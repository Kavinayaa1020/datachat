```python
"""
app.py
------
FastAPI backend for the iTech AI Innovation Hackathon 2026 project:
"Building Intelligent LLM Agents for Database Interaction & Visualization".

Endpoints:
  GET  /api/health          -> liveness check
  GET  /api/schema          -> raw DB schema (convenience, bypasses the LLM)
  POST /api/chat            -> main conversational endpoint (Gemini agent)
  POST /api/session/reset   -> clear a session's chat history

Run:
    uvicorn app:app --reload --port 8000
"""

import os
import uuid
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import tools
from seed_db import main as seed_database
from gemini_agent import run_agent_turn


DB_PATH = os.environ.get("DATABASE_PATH", "./ecommerce.db")


# Auto-seed the sample database on first run so the app works out of the box.
if not os.path.exists(DB_PATH):
    seed_database()


app = FastAPI(title="LLM DB Agent API", version="1.0.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://datachat-sigma.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# In-memory session store:
# session_id -> list[{"role": "user"/"assistant", "content": str}]
SESSIONS: Dict[str, List[Dict[str, str]]] = {}


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    artifacts: List[Dict[str, Any]]
    tool_trace: List[Dict[str, Any]]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/schema")
def schema():
    result = tools.get_schema()

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@app.post("/api/session/reset")
def reset_session(session_id: str):
    SESSIONS.pop(session_id, None)

    return {
        "status": "cleared",
        "session_id": session_id
    }


@app.get("/api/session/history")
def get_session_history(session_id: str):
    history = SESSIONS.get(session_id)

    if history is None:
        return {
            "session_id": session_id,
            "history": []
        }

    return {
        "session_id": session_id,
        "history": history
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history = SESSIONS.setdefault(session_id, [])

    if not req.message or not req.message.strip():
        raise HTTPException(
            status_code=400,
            detail="message must not be empty"
        )

    try:
        reply, artifacts, tool_trace = run_agent_turn(
            history,
            req.message
        )

    except RuntimeError as e:
        # e.g. missing API key
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {e}"
        )

    history.append({
        "role": "user",
        "content": req.message
    })

    history.append({
        "role": "assistant",
        "content": reply
    })

    # Keep session history bounded
    SESSIONS[session_id] = history[-40:]

    return ChatResponse(
        session_id=session_id,
        reply=reply,
        artifacts=artifacts,
        tool_trace=tool_trace,
    )
```
