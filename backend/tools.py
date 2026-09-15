"""
tools.py
--------
Implements the 5 required agent tools:

- get_schema
- execute_query
- generate_chart
- generate_flowchart
- explain_data

Every tool returns a plain JSON-serializable dict.
Tools never raise; they catch their own errors and return
{"error": "..."} so the LLM agent can read the error and recover.
"""

import base64
import io
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

import matplotlib

# Headless rendering - required for FastAPI/server environment
matplotlib.use("Agg")

import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("DATABASE_PATH", "./ecommerce.db")

MAX_ROWS = 500


# Only allow read-only SQL statements.
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


def _connect() -> sqlite3.Connection:
    """Create a SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ===========================================================================
# Tool 1: get_schema
# ===========================================================================

def get_schema(_: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Return tables, columns, types, primary keys,
    foreign keys, and row counts.
    """

    conn = None

    try:
        conn = _connect()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name NOT LIKE 'sqlite_%'
            """
        )

        tables = [row["name"] for row in cur.fetchall()]

        schema = {}

        for table in tables:

            # Columns
            cur.execute(f"PRAGMA table_info({table})")

            columns = [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "primary_key": bool(row["pk"]),
                    "not_null": bool(row["notnull"]),
                }
                for row in cur.fetchall()
            ]

            # Foreign keys
            cur.execute(f"PRAGMA foreign_key_list({table})")

            foreign_keys = [
                {
                    "column": row["from"],
                    "references_table": row["table"],
                    "references_column": row["to"],
                }
                for row in cur.fetchall()
            ]

            # Row count
            cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
            row_count = cur.fetchone()["c"]

            schema[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "row_count": row_count,
            }

        return {
            "tables": schema
        }

    except Exception as e:

        return {
            "error": f"get_schema failed: {type(e).__name__}: {e}"
        }

    finally:

        if conn is not None:
            conn.close()


# ===========================================================================
# Tool 2: execute_query
# ===========================================================================

def execute_query(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a read-only SQL SELECT query.
    """

    conn = None

    try:

        args = args or {}

        sql = str(args.get("sql", "")).strip()

        if not sql:
            return {
                "error": "No SQL provided."
            }

        upper_sql = sql.lstrip().upper()

        # Only SELECT or WITH
        if not (
            upper_sql.startswith("SELECT")
            or upper_sql.startswith("WITH")
        ):
            return {
                "error": (
                    "Only SELECT (or WITH ... SELECT) "
                    "statements are allowed."
                )
            }

        # Prevent dangerous statements
        if FORBIDDEN_KEYWORDS.search(sql):

            return {
                "error": (
                    "Query contains a forbidden keyword. "
                    "Only read-only SELECT queries are permitted."
                )
            }

        # Prevent multiple statements
        cleaned_sql = sql.strip().rstrip(";")

        if ";" in cleaned_sql:

            return {
                "error": "Multiple statements are not allowed."
            }

        conn = _connect()

        cur = conn.cursor()

        cur.execute(sql)

        rows = cur.fetchmany(MAX_ROWS)

        columns = (
            [description[0] for description in cur.description]
            if cur.description
            else []
        )

        data = [
            dict(row)
            for row in rows
        ]

        truncated = len(data) == MAX_ROWS

        return {
            "sql": sql,
            "columns": columns,
            "row_count": len(data),
            "truncated": truncated,
            "rows": data,
        }

    except Exception as e:

        return {
            "error": f"execute_query failed: {type(e).__name__}: {e}",
            "sql": sql if "sql" in locals() else "",
        }

    finally:

        if conn is not None:
            conn.close()


# ===========================================================================
# Tool 3: generate_chart
# ===========================================================================
def generate_chart(args: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a chart and return it as a base64 PNG."""
    try:
        args = args or {}

        chart_type = str(args.get("chart_type", "bar")).lower()
        title = str(args.get("title", "Chart"))

        labels = args.get("labels", [])
        values = args.get("values", [])

        x_label = str(args.get("x_label", ""))
        y_label = str(args.get("y_label", ""))

        if not labels:
            return {"error": "No labels provided."}

        if not values:
            return {"error": "No values provided."}

        if len(labels) != len(values):
            return {
                "error": "labels and values must have the same length."
            }

        # Convert values safely
        clean_values = []
        for v in values:
            clean_values.append(float(v))

        # Create figure
        fig = plt.figure(figsize=(8, 5))
        ax = fig.add_subplot(111)

        if chart_type == "bar":
            x = list(range(len(labels)))
            ax.bar(x, clean_values)

            ax.set_xticks(x)
            ax.set_xticklabels(
                [str(x) for x in labels],
                rotation=30,
                ha="right"
            )

        elif chart_type == "line":
            x = list(range(len(labels)))
            ax.plot(x, clean_values, marker="o")

            ax.set_xticks(x)
            ax.set_xticklabels(
                [str(x) for x in labels],
                rotation=30,
                ha="right"
            )

        elif chart_type == "pie":
            ax.pie(
                clean_values,
                labels=[str(x) for x in labels],
                autopct="%1.1f%%"
            )

        elif chart_type == "scatter":
            x = list(range(len(labels)))
            ax.scatter(x, clean_values)

            ax.set_xticks(x)
            ax.set_xticklabels(
                [str(x) for x in labels],
                rotation=30,
                ha="right"
            )

        else:
            plt.close(fig)
            return {
                "error": f"Unsupported chart type: {chart_type}"
            }

        ax.set_title(title)

        if chart_type != "pie":
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)

        fig.tight_layout()

        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        buffer.seek(0)

        encoded = base64.b64encode(buffer.read()).decode("utf-8")

        plt.close(fig)

        return {
            "artifact_type": "image",
            "format": "png",
            "title": title,
            "chart_type": chart_type,
            "data_base64": encoded
        }

    except Exception as e:
        try:
            plt.close("all")
        except Exception:
            pass

        return {
            "error": f"generate_chart failed: {type(e).__name__}: {e}"
        }


# ===========================================================================
# Tool 4: generate_flowchart
# ===========================================================================

def generate_flowchart(
    args: Dict[str, Any]
) -> Dict[str, Any]:

    """
    Generate a Mermaid diagram.

    diagram_type:
        er
        flowchart
        decision_tree
    """

    try:

        args = args or {}

        diagram_type = str(
            args.get(
                "diagram_type",
                "flowchart"
            )
        ).lower()

        title = str(
            args.get("title", "")
        )

        # ===============================================================
        # ER DIAGRAM
        # ===============================================================

        if diagram_type == "er":

            restrict = set(
                args.get("tables") or []
            )

            schema = get_schema()

            if "error" in schema:

                return schema

            lines = [
                "erDiagram"
            ]

            tables = schema["tables"]

            wanted = (
                restrict
                if restrict
                else set(tables.keys())
            )

            # Tables
            for table_name, table_info in tables.items():

                if table_name not in wanted:
                    continue

                lines.append(
                    f"    {table_name} {{"
                )

                for column in table_info["columns"]:

                    column_type = (
                        column["type"]
                        or "TEXT"
                    )

                    column_type = (
                        column_type
                        .split("(")[0]
                        .lower()
                        or "text"
                    )

                    pk = (
                        " PK"
                        if column["primary_key"]
                        else ""
                    )

                    lines.append(
                        f"        "
                        f"{column_type} "
                        f"{column['name']}"
                        f"{pk}"
                    )

                lines.append(
                    "    }"
                )

            # Relationships
            for table_name, table_info in tables.items():

                if table_name not in wanted:
                    continue

                for fk in table_info["foreign_keys"]:

                    if (
                        fk["references_table"]
                        in wanted
                    ):

                        lines.append(
                            f'    '
                            f'{fk["references_table"]} '
                            f'||--o{{ '
                            f'{table_name} '
                            f': "has"'
                        )

            mermaid_code = "\n".join(
                lines
            )

        # ===============================================================
        # FLOWCHART / DECISION TREE
        # ===============================================================

        elif diagram_type in (
            "flowchart",
            "decision_tree",
        ):

            nodes = args.get(
                "nodes"
            ) or []

            edges = args.get(
                "edges"
            ) or []

            if not nodes:

                return {
                    "error": (
                        "generate_flowchart requires "
                        "'nodes' for "
                        "flowchart/decision_tree "
                        "diagrams."
                    )
                }

            lines = [
                "flowchart TD"
            ]

            shape_map = {

                "rect": (
                    "[",
                    "]"
                ),

                "round": (
                    "(",
                    ")"
                ),

                "diamond": (
                    "{",
                    "}"
                ),

                "stadium": (
                    "([",
                    "])"
                ),
            }

            # Nodes
            for node in nodes:

                node_id = str(
                    node.get("id", "")
                )

                if not node_id:

                    continue

                label = str(
                    node.get(
                        "label",
                        node_id
                    )
                )

                label = label.replace(
                    '"',
                    "'"
                )

                shape = node.get(
                    "shape",
                    "rect"
                )

                open_shape, close_shape = (
                    shape_map.get(
                        shape,
                        (
                            "[",
                            "]"
                        )
                    )
                )

                lines.append(
                    f'    '
                    f'{node_id}'
                    f'{open_shape}'
                    f'"{label}"'
                    f'{close_shape}'
                )

            # Edges
            for edge in edges:

                source = str(
                    edge.get(
                        "from",
                        ""
                    )
                )

                target = str(
                    edge.get(
                        "to",
                        ""
                    )
                )

                if not source or not target:

                    continue

                label = edge.get(
                    "label"
                )

                if label:

                    lines.append(
                        f'    '
                        f'{source} '
                        f'-->|{label}| '
                        f'{target}'
                    )

                else:

                    lines.append(
                        f'    '
                        f'{source} '
                        f'--> '
                        f'{target}'
                    )

            mermaid_code = "\n".join(
                lines
            )

        else:

            return {
                "error": (
                    f"Unsupported diagram_type "
                    f"'{diagram_type}'. "
                    "Use er, flowchart, "
                    "or decision_tree."
                )
            }

        return {
            "artifact_type": "mermaid",
            "diagram_type": diagram_type,
            "title": title,
            "mermaid_code": mermaid_code,
        }

    except Exception as e:

        return {
            "error": (
                f"generate_flowchart failed: "
                f"{type(e).__name__}: {e}"
            )
        }


# ===========================================================================
# Tool 5: explain_data
# ===========================================================================

def explain_data(
    args: Dict[str, Any]
) -> Dict[str, Any]:

    """
    Produce structured statistical summaries.

    Expected args:
        rows: list[dict]
        numeric_field: optional
        group_field: optional
    """

    try:

        args = args or {}

        rows: List[
            Dict[str, Any]
        ] = args.get(
            "rows"
        ) or []

        numeric_field = args.get(
            "numeric_field"
        )

        group_field = args.get(
            "group_field"
        )

        # No rows
        if not rows:

            return {
                "summary_facts": {
                    "row_count": 0
                },
                "note": "No rows to analyze.",
            }

        facts: Dict[
            str,
            Any
        ] = {
            "row_count": len(rows)
        }

        # ===============================================================
        # NUMERIC STATISTICS
        # ===============================================================

        if (
            numeric_field
            and numeric_field in rows[0]
        ):

            values = []

            for row in rows:

                value = row.get(
                    numeric_field
                )

                if isinstance(
                    value,
                    (int, float)
                ):

                    values.append(
                        value
                    )

            if values:

                total = sum(values)

                average = (
                    total / len(values)
                )

                facts[
                    "numeric_field"
                ] = numeric_field

                facts[
                    "sum"
                ] = round(
                    total,
                    2
                )

                facts[
                    "avg"
                ] = round(
                    average,
                    2
                )

                facts[
                    "min"
                ] = min(values)

                facts[
                    "max"
                ] = max(values)

        # ===============================================================
        # GROUP STATISTICS
        # ===============================================================

        if (
            group_field
            and group_field in rows[0]
        ):

            groups: Dict[
                str,
                float
            ] = {}

            for row in rows:

                key = str(
                    row.get(
                        group_field
                    )
                )

                if numeric_field:

                    value = row.get(
                        numeric_field,
                        1
                    )

                else:

                    value = 1

                if not isinstance(
                    value,
                    (int, float)
                ):

                    value = 1

                groups[key] = (
                    groups.get(
                        key,
                        0
                    )
                    + value
                )

            top = sorted(
                groups.items(),
                key=lambda item: item[1],
                reverse=True
            )[:10]

            facts[
                "group_field"
            ] = group_field

            facts[
                "top_groups"
            ] = [
                {
                    "group": key,
                    "total": round(
                        value,
                        2
                    ),
                }
                for key, value in top
            ]

        return {
            "summary_facts": facts
        }

    except Exception as e:

        return {
            "error": (
                f"explain_data failed: "
                f"{type(e).__name__}: {e}"
            )
        }


# ===========================================================================
# Tool dispatch table
# ===========================================================================

TOOL_FUNCTIONS = {

    "get_schema": get_schema,

    "execute_query": execute_query,

    "generate_chart": generate_chart,

    "generate_flowchart": generate_flowchart,

    "explain_data": explain_data,

}