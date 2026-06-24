"""
Bullseye data tools — the existing MCP server, reused as-is (migration plan,
Phase 2). We spawn `bullseye-mcp/server.py` over stdio with a per-request,
per-user env (JWT + workspace + active school) and adapt its tools into
LangChain via `langchain-mcp-adapters`. None of the careful endpoint, offload,
or pagination work is rewritten — only the transport changes.

One stdio subprocess lives for the duration of one chat turn (the async context
manager below), mirroring how the Agent SDK spawned the MCP server per query.
User JWTs never cross turns because each turn gets its own subprocess + env.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from bullseye_copilot.core.config import MCP_DIR, MCP_PYTHON, MCP_SERVER

log = logging.getLogger("copilot.mcp")

# The read/write tools the agent is allowed to use — the exact allowlist the
# Agent-SDK gateway granted. `get_auth_token` (token injected via env) and
# `set_active_school` (school injected via env) are intentionally excluded.
ALLOWED_TOOLS = {
    "get_school_context",
    "list_sessions",
    "get_session",
    "get_active_goal",
    "get_goal_history",
    "next_steps_read",
    "get_person_records",
    "get_objective_detail",
    "get_dashboard",
    "next_steps_write",  # the one write surface — governed by the confirm-first rule
}


def _server_env(token: str, workdir: Path, school_id: str | None) -> dict:
    """Per-subprocess env for this request's user only — never enters the model's
    context. BULLSEYE_WORKDIR switches the heavy tools to file-mode (./data/*.json);
    BULLSEYE_SCHOOL_ID scopes calls to the user's active school."""
    env = {
        **os.environ,  # inherit PATH etc. so the venv python resolves
        "BULLSEYE_TOKEN": token,
        "BULLSEYE_WORKDIR": str(workdir),
    }
    if school_id:
        env["BULLSEYE_SCHOOL_ID"] = str(school_id)
    return env


@asynccontextmanager
async def bullseye_tools(token: str, workdir: Path, school_id: str | None):
    """Yield the allowlisted Bullseye tools, keeping one stdio MCP session open
    for the lifetime of the `async with` block (i.e. one chat turn)."""
    client = MultiServerMCPClient(
        {
            "bullseye": {
                "transport": "stdio",
                "command": str(MCP_PYTHON),
                "args": [str(MCP_SERVER)],
                "cwd": str(MCP_DIR),
                "env": _server_env(token, workdir, school_id),
            }
        }
    )
    async with client.session("bullseye") as session:
        tools = await load_mcp_tools(session)
        allowed = [t for t in tools if t.name in ALLOWED_TOOLS]
        log.info("loaded %d Bullseye MCP tools (%d allowed)", len(tools), len(allowed))
        yield allowed
