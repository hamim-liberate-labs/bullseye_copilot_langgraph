"""
Chat endpoints — the heart of the gateway.

Same HTTP contract as the Agent-SDK build (`/api/chat`, `/api/chat/stream`), so
the existing frontend is unchanged. Each turn builds a LangGraph ReAct agent over
the reused Bullseye MCP tools plus the workspace file/bash/web tools, and streams
its output as the SSE events the frontend already parses.

Two ids per conversation:
  • chat_id    — the artifact workspace folder (file-tool isolation boundary)
  • session_id — the LangGraph thread_id for conversation memory (checkpointer)
"""

import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphRecursionError

from bullseye_copilot.api.v1.schemas.chat import ChatRequest
from bullseye_copilot.core.config import RECURSION_LIMIT
from bullseye_copilot.llm.workflows.copilot.agent import build_agent
from bullseye_copilot.llm.workflows.copilot.tools.bullseye_mcp import bullseye_tools
from bullseye_copilot.utils.streaming import (
    HEARTBEAT_SECONDS,
    TOOL_LABELS,
    MarkerFilter,
    chunk_text,
    sse,
)
from bullseye_copilot.utils.usage import TurnUsage
from bullseye_copilot.utils.workspace import (
    ID_RE,
    ensure_workspace,
    extract_artifact_marker,
    scan_artifacts,
)

log = logging.getLogger("gateway")

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _is_recursion_limit(exc: BaseException) -> bool:
    """True if `exc` is — or wraps, via an anyio ExceptionGroup — a
    GraphRecursionError. The limit error propagates out of the MCP stdio session's
    task group wrapped in (possibly nested) ExceptionGroups, so a plain
    `except GraphRecursionError` would miss it."""
    if isinstance(exc, GraphRecursionError):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_recursion_limit(e) for e in exc.exceptions)
    return False


def _is_transient_overload(exc: BaseException) -> bool:
    """True if `exc` is — or wraps, via an anyio ExceptionGroup — a transient,
    retryable provider error (HTTP 529 'Overloaded', 503). These arrive wrapped in
    the same nested ExceptionGroups as the recursion error, and when they surface
    mid-stream the provider SDK can no longer auto-retry them, so we catch them here
    and return a friendly 'try again' instead of a stack trace. Provider-agnostic:
    matches on the HTTP status / message rather than importing a specific SDK."""
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_transient_overload(e) for e in exc.exceptions)
    if getattr(exc, "status_code", None) in (503, 529):
        return True
    return "overloaded" in str(exc).lower()


def _school_id(body: ChatRequest) -> str | None:
    school = (body.user or {}).get("current_school") or {}
    sid = school.get("id")
    return str(sid) if sid is not None else None


def _run_config(session_id: str) -> dict:
    return {
        "configurable": {"thread_id": session_id},
        "recursion_limit": RECURSION_LIMIT,
    }


def _ids(body: ChatRequest) -> tuple[str, str]:
    chat_id = body.chat_id or uuid.uuid4().hex
    if not ID_RE.match(chat_id):
        raise HTTPException(status_code=400, detail="invalid chat_id")
    session_id = body.session_id or uuid.uuid4().hex
    return chat_id, session_id


# ── Non-streaming ──────────────────────────────────────────────────────────────


@router.post("/api/chat")
async def chat(body: ChatRequest) -> dict:
    chat_id, session_id = _ids(body)
    workdir = ensure_workspace(chat_id)

    t0 = time.monotonic()
    log.info("chat (non-stream) start · chat=%s msg=%r", chat_id, body.message[:80])

    async with bullseye_tools(body.token, workdir, _school_id(body)) as bt:
        agent = build_agent(
            bullseye_tools=bt, workdir=workdir, user=body.user,
            model_alias=body.model, effort=body.effort,
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": body.message}]},
            config=_run_config(session_id),
        )

    usage = TurnUsage()
    for m in result["messages"]:
        usage.add(m)
    log.info("chat (non-stream) done in %.1fs · usage · %s",
             time.monotonic() - t0, usage.summary())

    reply = chunk_text(result["messages"][-1])
    if not reply:
        raise HTTPException(status_code=502, detail="agent did not produce a reply")

    reply, active_artifact = extract_artifact_marker(reply, chat_id, workdir)
    return {
        "reply": reply,
        "session_id": session_id,
        "chat_id": chat_id,
        "active_artifact": active_artifact,
        "artifacts": scan_artifacts(chat_id, workdir),
        "cost_usd": round(usage.cost, 6),
    }


# ── Streaming (SSE) ─────────────────────────────────────────────────────────--


@router.post("/api/chat/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    chat_id, session_id = _ids(body)
    workdir = ensure_workspace(chat_id)

    turn = uuid.uuid4().hex[:8]
    log.info(
        "[%s] turn start · chat=%s resume=%s msg=%r",
        turn, chat_id, body.session_id or "new", body.message[:80],
    )

    async def event_stream():
        t0 = time.monotonic()
        elapsed = lambda: f"{time.monotonic() - t0:6.1f}s"
        marker_filter = MarkerFilter()
        # Text of the *current* model run; reset each run so `reply` holds the
        # final answer (the last run), not interleaved tool-call turns.
        run_text: list[str] = []
        reply_parts: list[str] = []
        usage = TurnUsage()
        tool_calls = 0
        first_text = True

        # Producer feeds SSE frames through this queue; the consumer drains it and
        # emits keepalives during idle gaps so a proxy never times us out.
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def produce() -> None:
            nonlocal tool_calls, first_text, reply_parts
            try:
                async with bullseye_tools(body.token, workdir, _school_id(body)) as bt:
                    agent = build_agent(
                        bullseye_tools=bt, workdir=workdir, user=body.user,
                        model_alias=body.model, effort=body.effort,
                    )
                    async for ev in agent.astream_events(
                        {"messages": [{"role": "user", "content": body.message}]},
                        config=_run_config(session_id),
                        version="v2",
                    ):
                        kind = ev["event"]
                        # Only the agent's own model node ("model") produces the
                        # user-facing reply. Other model calls in the graph — most
                        # importantly the SummarizationMiddleware writing a history
                        # summary — must NOT be streamed to the user or mistaken for
                        # the reply, or summary text would leak into the chat once a
                        # long conversation crosses the summarization trigger.
                        node = (ev.get("metadata") or {}).get("langgraph_node")
                        is_agent_model = node == "model"
                        if kind == "on_chat_model_start":
                            if is_agent_model:
                                run_text.clear()  # a new agent run begins; last run wins
                        elif kind == "on_chat_model_stream":
                            if is_agent_model:
                                text = chunk_text(ev["data"]["chunk"])
                                if text:
                                    run_text.append(text)
                                    shown = marker_filter.feed(text)
                                    if shown:
                                        if first_text:
                                            log.info("[%s] %s first text", turn, elapsed())
                                            first_text = False
                                        await queue.put(sse("text", {"delta": shown}))
                        elif kind == "on_chat_model_end":
                            # Count every model call's tokens for cost (agent +
                            # summarizer), but only the agent runs feed the reply.
                            usage.add(ev["data"]["output"])
                            if is_agent_model:
                                reply_parts = list(run_text)
                        elif kind == "on_tool_start":
                            name = ev.get("name", "")
                            tool_calls += 1
                            log.info("[%s] %s tool · %s", turn, elapsed(), name)
                            await queue.put(sse(
                                "tool",
                                {"name": name, "label": TOOL_LABELS.get(name, "Working…")},
                            ))

                tail = marker_filter.flush()
                if tail:
                    await queue.put(sse("text", {"delta": tail}))

                reply = "".join(reply_parts).strip()
                if not reply:
                    log.error("[%s] %s no reply", turn, elapsed())
                    await queue.put(sse("error", {"detail": "agent did not produce a reply"}))
                    return

                cleaned, active_artifact = extract_artifact_marker(reply, chat_id, workdir)
                log.info(
                    "[%s] %s done · %d tool calls · reply=%d chars · artifact=%s",
                    turn, elapsed(), tool_calls, len(cleaned),
                    active_artifact["thread"] if active_artifact else "none",
                )
                log.info("[%s] %s usage · %s", turn, elapsed(), usage.summary())
                await queue.put(sse(
                    "result",
                    {
                        "reply": cleaned,
                        "session_id": session_id,
                        "chat_id": chat_id,
                        "active_artifact": active_artifact,
                        "artifacts": scan_artifacts(chat_id, workdir),
                        "cost_usd": round(usage.cost, 6),
                    },
                ))
            except Exception as exc:  # surface agent failures as an SSE event
                # Hitting the step cap is expected on very heavy turns — don't
                # crash, return whatever the agent produced (text + any artifact
                # it already built) so the work isn't lost.
                if _is_recursion_limit(exc):
                    log.warning("[%s] %s step cap reached — returning partial work", turn, elapsed())
                    log.info("[%s] %s usage · %s", turn, elapsed(), usage.summary())
                    tail = marker_filter.flush()
                    if tail:
                        await queue.put(sse("text", {"delta": tail}))
                    reply = (
                        "".join(reply_parts).strip()
                        or "".join(run_text).strip()
                        or (
                            "I gathered a lot but ran out of room to finish that in one "
                            "go. Try narrowing it — a single chart, one person, or a "
                            "shorter date range — and I'll build on what I've pulled."
                        )
                    )
                    cleaned, active_artifact = extract_artifact_marker(reply, chat_id, workdir)
                    await queue.put(sse(
                        "result",
                        {
                            "reply": cleaned,
                            "session_id": session_id,
                            "chat_id": chat_id,
                            "active_artifact": active_artifact,
                            "artifacts": scan_artifacts(chat_id, workdir),
                            "cost_usd": round(usage.cost, 6),
                        },
                    ))
                    return
                # Transient provider overload (529/503): retryable and not our bug,
                # so log a one-line warning (not the full traceback) and tell the
                # user to retry rather than surfacing a raw ExceptionGroup string.
                if _is_transient_overload(exc):
                    log.warning("[%s] %s provider overloaded — retryable", turn, elapsed())
                    await queue.put(sse("error", {
                        "detail": "The model provider is temporarily overloaded. "
                                  "Please try again in a moment.",
                        "retryable": True,
                    }))
                    return
                log.exception("[%s] %s stream failed", turn, elapsed())
                await queue.put(sse("error", {"detail": str(exc)}))
            finally:
                await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # resets the proxy idle-read timer
                    continue
                if frame is None:
                    break
                yield frame
        finally:
            producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
