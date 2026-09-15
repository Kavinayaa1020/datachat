"""
gemini_agent.py
----------------
Wraps the Gemini API (the `google-genai` SDK -- the current, supported
successor to the deprecated `google-generativeai` package) with manual
function-calling so the model can invoke our 5 tools (see tools.py) to
answer natural-language questions about the database, and to produce
charts/flowcharts.

The agent loop:
  1. Send the running conversation history to Gemini with the tool schemas.
  2. If Gemini responds with one or more function_call parts, execute the
     matching Python function from tools.TOOL_FUNCTIONS.
  3. Feed the function result(s) back to Gemini as function_response parts.
  4. Repeat until Gemini returns a plain text answer (or we hit MAX_STEPS).

Any artifacts produced by generate_chart / generate_flowchart along the way
are collected and returned to the API layer so the frontend can render them
inline in the chat, alongside the model's final natural-language reply.
"""
import time
import os
import json
from typing import Any, Dict, List, Tuple

from google import genai
from google.genai import types

from tools import TOOL_FUNCTIONS

MAX_STEPS = 6  # safety cap on tool-call round-trips per user turn

SYSTEM_INSTRUCTION = """You are DataChat, an expert conversational data analyst \
embedded in a business-intelligence chat application. You help non-technical \
users explore a company e-commerce SQLite database (tables: customers, \
products, orders, order_items, inventory) using natural language.

Guidelines:
- If you are not certain of the exact table/column names, call get_schema first.
- Always use execute_query (SELECT-only) to fetch real data before answering \
factual/numeric questions. Never invent numbers.
- When the user asks to "show", "plot", "chart", or "visualize" data, call \
generate_chart with the real rows you retrieved (pick sensible chart_type: \
bar for comparisons across categories, line for trends over time, pie for \
proportions of a whole, scatter for correlation between two numeric fields).
- When the user asks for an ER diagram, schema diagram, or process/flow \
diagram, call generate_flowchart (diagram_type "er" for database structure, \
"flowchart" for processes/pipelines, "decision_tree" for conditional logic).
- Use explain_data to compute accurate statistics (sums, averages, top \
groups) before writing an explanation -- do not do mental arithmetic on \
large result sets yourself.
- Before running a query, briefly mention in your final answer what SQL you \
used so the user can verify it (SQL transparency).
- Keep replies concise, friendly, and focused on insights, not just raw data \
dumps. Use bullet points for lists of findings.
- If a tool returns an error, explain briefly what went wrong and try a \
corrected approach (e.g. re-check column names via get_schema) rather than \
giving up immediately.
"""

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_schema",
        description="Retrieve the full database schema: tables, columns, types, "
                    "primary/foreign keys, and row counts. Call this whenever you "
                    "are unsure of exact table or column names.",
        parameters={"type": "OBJECT", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="execute_query",
        description="Execute a read-only SQL SELECT query against the SQLite "
                    "database and return the resulting rows as JSON. Only "
                    "SELECT/WITH statements are permitted.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "sql": {"type": "STRING", "description": "A single SELECT SQL statement."}
            },
            "required": ["sql"],
        },
    ),
    types.FunctionDeclaration(
        name="generate_chart",
        description="Render a bar, line, pie, or scatter chart from tabular "
                    "data and return it as a base64-encoded PNG image.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "chart_type": {"type": "STRING", "enum": ["bar", "line", "pie", "scatter"]},
                "title": {"type": "STRING"},
                "x_label": {"type": "STRING"},
                "y_label": {"type": "STRING"},
                "labels": {"type": "ARRAY", "items": {"type": "STRING"},
                           "description": "Category/x-axis labels."},
                "values": {"type": "ARRAY", "items": {"type": "NUMBER"},
                           "description": "Single data series matching 'labels'."},
            },
            "required": ["chart_type", "labels"],
        },
    ),
    types.FunctionDeclaration(
        name="generate_flowchart",
        description="Generate a Mermaid diagram: an Entity-Relationship (ER) "
                    "diagram of the live database schema, or a custom "
                    "flowchart/decision-tree from nodes and edges you supply.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "diagram_type": {"type": "STRING",
                                  "enum": ["er", "flowchart", "decision_tree"]},
                "title": {"type": "STRING"},
                "tables": {"type": "ARRAY", "items": {"type": "STRING"},
                           "description": "Optional: restrict ER diagram to these tables."},
                "nodes": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "id": {"type": "STRING"},
                            "label": {"type": "STRING"},
                            "shape": {"type": "STRING",
                                      "enum": ["rect", "round", "diamond", "stadium"]},
                        },
                        "required": ["id", "label"],
                    },
                    "description": "Required for flowchart/decision_tree diagrams.",
                },
                "edges": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "from": {"type": "STRING"},
                            "to": {"type": "STRING"},
                            "label": {"type": "STRING"},
                        },
                        "required": ["from", "to"],
                    },
                },
            },
            "required": ["diagram_type"],
        },
    ),
    types.FunctionDeclaration(
        name="explain_data",
        description="Compute accurate summary statistics (sum, avg, min, max, "
                    "top groups) over a set of rows so you can write a "
                    "reliable natural-language explanation without doing "
                    "manual arithmetic.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "rows": {"type": "ARRAY", "items": {"type": "OBJECT"},
                         "description": "Rows returned by execute_query."},
                "numeric_field": {"type": "STRING"},
                "group_field": {"type": "STRING"},
            },
            "required": ["rows"],
        },
    ),
]

_TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy backend/.env.example to "
                "backend/.env and add your key."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _history_to_genai_contents(history: List[Dict[str, str]]) -> List[types.Content]:
    """Convert our simple [{role, content}] session history into genai Content objects."""
    contents = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn["content"])]))
    return contents


def run_agent_turn(history: List[Dict[str, str]], user_message: str
                    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Run one full agent turn (including any tool-call round trips).

    Returns:
      final_text: the model's final natural-language reply
      artifacts:  list of chart/mermaid artifact dicts to render in the UI
      tool_trace: list of {tool, args, result} for transparency (e.g. SQL used)
    """
    client = _get_client()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=_TOOLS,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    chat = client.chats.create(
        model=model_name,
        config=config,
        history=_history_to_genai_contents(history),
    )

    artifacts: List[Dict[str, Any]] = []
    tool_trace: List[Dict[str, Any]] = []

    response = chat.send_message(user_message)

    for _ in range(MAX_STEPS):
        calls = response.function_calls or []
        if not calls:
            break

        function_response_parts = []
        for fc in calls:
            tool_name = fc.name
            args = dict(fc.args) if fc.args else {}
            func = TOOL_FUNCTIONS.get(tool_name)

            if func is None:
                result = {"error": f"Unknown tool '{tool_name}'"}
            else:
                result = func(args)

            # Collect visual artifacts for the frontend
            if isinstance(result, dict) and result.get("artifact_type") in ("image", "mermaid"):
                artifacts.append(result)

            # Build a lightweight trace entry (skip huge base64 blobs / row dumps)
            trace_result = {k: v for k, v in result.items()
                             if k not in ("data_base64", "rows")}
            if isinstance(result, dict) and "rows" in result:
                trace_result["row_count"] = result.get("row_count")
            tool_trace.append({"tool": tool_name, "args": args, "result": trace_result})

            function_response_parts.append(
                types.Part(function_response=types.FunctionResponse(
                    name=tool_name, response={"result": _safe_json(result)}
                ))
            )

        response = chat.send_message(function_response_parts)

    final_text = response.text or ""

    if not final_text:
        final_text = ("I gathered the data and generated the visualization(s) "
                       "above. Let me know if you'd like me to go deeper on "
                       "any part of it.")

    return final_text, artifacts, tool_trace


def _safe_json(obj: Any) -> Any:
    """Ensure the object is JSON-serializable for Gemini's function_response."""
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        return json.loads(json.dumps(obj, default=str))
