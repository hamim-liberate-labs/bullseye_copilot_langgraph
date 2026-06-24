"""
Streaming plumbing for the SSE chat endpoint.

Reproduces the exact wire signals the frontend already expects (api.ts):
  event: tool   {name, label}     — a tool started; show its friendly label
  event: text   {delta}           — a chunk of the streamed reply
  event: result {ChatResult}      — authoritative final payload
  event: error  {detail}          — failure

Includes the <artifact>…</artifact> marker suppressor and the human-readable
tool labels.
"""

import json

# Friendly status labels keyed by tool name. MCP tool names are now bare
# (e.g. "list_sessions") since langchain-mcp-adapters drops the mcp__bullseye__
# prefix; workspace tools use their snake_case names.
TOOL_LABELS = {
    "get_school_context": "Loading school context…",
    "get_dashboard": "Opening the dashboard…",
    "list_sessions": "Looking through sessions…",
    "get_session": "Reading a session…",
    "get_active_goal": "Looking up the active goal…",
    "get_goal_history": "Reviewing goal history…",
    "get_person_records": "Reviewing the profile…",
    "get_objective_detail": "Reviewing objective scores…",
    "next_steps_read": "Checking next steps…",
    "next_steps_write": "Updating next steps…",
    "write_file": "Building the artifact…",
    "edit_file": "Updating the artifact…",
    "read_file": "Reviewing the artifact…",
    "bash": "Crunching the data…",
    "web_fetch": "Looking something up…",
    "web_search": "Searching the web…",
}

_MARKER_OPEN = "<artifact>"
_MARKER_CLOSE = "</artifact>"

# How long the stream may sit idle (a long tool call with no model output)
# before we emit an SSE keepalive comment. Stay under any reverse-proxy read
# timeout in front of the gateway (nginx defaults to 60s).
HEARTBEAT_SECONDS = 15


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def chunk_text(chunk) -> str:
    """Extract user-visible text from an AIMessageChunk/AIMessage. Anthropic
    content may be a plain string or a list of blocks; we keep only `text` blocks
    (skipping thinking / tool_use blocks)."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


class MarkerFilter:
    """Suppress <artifact>…</artifact> from a stream of text deltas.

    Holds back any tail that could be the start of a marker, so the tag never
    flashes in the UI even when it's split across deltas. The final `result`
    event remains authoritative for the artifact itself.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_marker = False

    def feed(self, text: str) -> str:
        self._buf += text
        out = ""
        while True:
            if self._in_marker:
                idx = self._buf.find(_MARKER_CLOSE)
                if idx == -1:
                    return out  # keep buffering until the close tag arrives
                self._buf = self._buf[idx + len(_MARKER_CLOSE):]
                self._in_marker = False
            else:
                idx = self._buf.find(_MARKER_OPEN)
                if idx != -1:
                    out += self._buf[:idx]
                    self._buf = self._buf[idx + len(_MARKER_OPEN):]
                    self._in_marker = True
                    continue
                # emit everything except a tail that could be a partial open tag
                keep = 0
                for k in range(min(len(_MARKER_OPEN) - 1, len(self._buf)), 0, -1):
                    if _MARKER_OPEN.startswith(self._buf[-k:]):
                        keep = k
                        break
                emit_to = len(self._buf) - keep
                out += self._buf[:emit_to]
                self._buf = self._buf[emit_to:]
                return out

    def flush(self) -> str:
        """Release anything held back (call once the stream ends)."""
        out = "" if self._in_marker else self._buf
        self._buf = ""
        self._in_marker = False
        return out
