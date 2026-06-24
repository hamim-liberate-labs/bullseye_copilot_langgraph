"""Chat request model. Matches the Agent-SDK gateway's contract exactly so the
existing frontend (frontend/src/lib/api.ts) talks to this backend unchanged."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    token: str  # Bullseye JWT from /api/login — injected into the MCP subprocess env
    message: str
    session_id: str | None = None  # omit on first turn; pass back for follow-ups (LangGraph thread_id)
    chat_id: str | None = None  # artifact workspace id; returned on first turn, pass back
    user: dict | None = None  # the user object from /api/login, personalizes the prompt
    model: str | None = None  # "opus"/"sonnet"/"haiku"; chosen in the UI per conversation
    effort: str | None = None  # reasoning effort: low/medium/high/xhigh/max
