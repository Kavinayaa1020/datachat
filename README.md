# DataChat — Conversational LLM Agent for Database Interaction & Visualization

Built for **iTech AI Innovation Hackathon 2026** — *Building Intelligent LLM
Agents for Database Interaction & Visualization*.

A ChatGPT-style app where a Gemini-powered agent understands natural-language
questions, queries a SQLite e-commerce database through custom tools, and
renders charts (bar/line/pie/scatter) and Mermaid diagrams (ER diagrams,
flowcharts) directly inline in the chat, with full SQL transparency.

---

## 1. Architecture

```
┌────────────────────┐        HTTP/JSON        ┌──────────────────────────────┐
│   Frontend (SPA)    │  ───────────────────▶   │        Backend (FastAPI)      │
│  index.html/app.js  │  ◀───────────────────   │           app.py              │
│  - chat UI          │      {reply, artifacts}  │  - session history (memory)  │
│  - mermaid.js render│                          │  - /api/chat, /api/schema     │
└────────────────────┘                          └───────────────┬───────────────┘
                                                                  │
                                                                  ▼
                                                  ┌──────────────────────────────┐
                                                  │      gemini_agent.py          │
                                                  │  Gemini function-calling loop  │
                                                  │  (Google Generative AI SDK)    │
                                                  └───────────────┬───────────────┘
                                                                  │ tool calls
                                                                  ▼
                                                  ┌──────────────────────────────┐
                                                  │           tools.py            │
                                                  │  get_schema · execute_query   │
                                                  │  generate_chart · generate_   │
                                                  │  flowchart · explain_data     │
                                                  └───────────────┬───────────────┘
                                                                  ▼
                                                     ecommerce.db (SQLite, seeded
                                                     by seed_db.py: customers,
                                                     products, orders, order_items,
                                                     inventory)
```

**Flow for a turn:** user message → backend forwards conversation + tool
schemas to Gemini → Gemini emits `function_call` parts → backend executes the
matching Python function → result fed back to Gemini as `function_response` →
loop continues (up to `MAX_STEPS`) until Gemini returns plain text → backend
returns `{reply, artifacts, tool_trace}` → frontend renders the text, any
chart images / Mermaid diagrams, and a collapsible "tool trace" panel showing
the exact SQL and tool arguments used (SQL transparency, per the bonus spec).

---

## 2. Agent tools

| Tool | Purpose | Output |
|---|---|---|
| `get_schema` | Introspects SQLite (`sqlite_master`, `PRAGMA table_info/foreign_key_list`) | JSON: tables → columns/types/PK/FK + row counts |
| `execute_query` | Runs a **read-only** `SELECT`/`WITH` statement (blocks `INSERT/UPDATE/DELETE/DROP/ALTER/...`, blocks multiple statements) | JSON rows, columns, row count |
| `generate_chart` | Renders bar / line / pie / scatter charts with Matplotlib | base64 PNG artifact |
| `generate_flowchart` | Builds Mermaid `erDiagram` from the live schema, or a custom `flowchart TD` / decision tree from nodes+edges | Mermaid source artifact (rendered client-side) |
| `explain_data` | Computes sum/avg/min/max and top-N group breakdowns over rows so the LLM explains with **real numbers**, not guesses | JSON summary facts |

All tools return `{"error": "..."}` on failure instead of raising, so the
agent can read the error and retry with a corrected approach (e.g. call
`get_schema` again after a bad column name).

---

## 3. Project layout

```
hackathon-app/
├── backend/
│   ├── app.py            # FastAPI app: /api/chat, /api/schema, /api/health
│   ├── gemini_agent.py    # Gemini function-calling loop + tool schemas
│   ├── tools.py           # 5 tool implementations
│   ├── seed_db.py         # Creates & seeds the sample SQLite database
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 4. Setup — run locally (no Docker)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set GEMINI_API_KEY=<your key from https://aistudio.google.com/app/apikey>

python seed_db.py               # creates ecommerce.db with sample data (optional — app.py auto-seeds on first run)
uvicorn app:app --reload --port 8000
```

Backend now runs at `http://localhost:8000`. Check `http://localhost:8000/api/health`.

### Frontend

The frontend is static — no build step needed.

```bash
cd frontend
python -m http.server 8080
```

Open `http://localhost:8080`. If your backend is on a different host/port,
edit the `window.DATACHAT_API_BASE` value at the top of `index.html`.

---

## 5. Setup — Docker (recommended)

```bash
cp backend/.env.example backend/.env
# edit backend/.env and add your GEMINI_API_KEY

docker compose up --build
```

- Frontend: `http://localhost:8080`
- Backend:  `http://localhost:8000`

---

## 6. Sample conversations to try

- "Show me the top 5 products by revenue this quarter" → bar chart + SQL used
- "Now show me the trend for those products over the last year" → line chart
- "Draw me the ER diagram for this database" → Mermaid ER diagram
- "Which tables are related to customers?" → text answer using schema
- "Create a flowchart showing how orders flow through our system" → custom Mermaid flowchart
- "Break down orders by status" → pie chart
- "Which customers have placed the most orders?" → table + explanation using `explain_data`

---

## 7. Design notes / trade-offs

- **Security:** `execute_query` allow-lists `SELECT`/`WITH` and blocks DDL/DML
  keywords and multi-statement queries as defense-in-depth. In production,
  pair this with a database role that only has `SELECT` grants.
- **Session state** is in-memory (`SESSIONS` dict in `app.py`) for hackathon
  simplicity — swap for Redis/Postgres for multi-instance deployments.
- **Charts** are rendered server-side with Matplotlib and returned as base64
  PNG, so no chart library is required client-side. Diagrams are Mermaid
  *source*, rendered client-side with `mermaid.js` (keeps the backend
  lightweight and the diagrams crisp/zoomable as SVG).
- **SQL transparency** (bonus): every tool call, including the exact SQL
  string, is returned in `tool_trace` and shown in a collapsible terminal-style
  panel under each agent reply.

## 8. Possible extensions (bonus challenges not yet implemented)

- True token-streaming (currently the reply streams as one JSON response per turn)
- Export chart as PNG/PDF download button, CSV export of query results
- Multi-database support (Postgres/MySQL/Mongo connectors alongside SQLite)
- Voice input (Web Speech API)
- Persist chat history & saved queries to a real database
- Dashboard builder to pin multiple artifacts together
