"""
Assemble the LangGraph ReAct agent for one chat turn.

Brings together: the per-request model (alias + effort), the full tool set
(reused Bullseye MCP tools + workspace files + bash + web), the reused system
prompt, a checkpointer for conversation memory (Phase 7), Anthropic prompt
caching (cost optimization), and — optionally — the enforced confirm-before-write
middleware (Phase 6).
"""

from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver

from bullseye_copilot.core.config import (
    BASH_SPIRAL_REPEAT,
    BASH_SPIRAL_THRESHOLD,
    CONTEXT_EDIT_KEEP,
    CONTEXT_EDIT_TRIGGER_TOKENS,
    ENABLE_CONTEXT_EDITING,
    ENABLE_HITL,
    ENABLE_SUMMARIZATION,
    KNOWLEDGE_DIR,
    SUMMARY_KEEP_MESSAGES,
    SUMMARY_MODEL,
    SUMMARY_TRIGGER_TOKENS,
    WRITE_FILE_RUN_LIMIT,
)
from bullseye_copilot.llm.models import build_model, provider_of
from bullseye_copilot.llm.workflows.copilot.middleware import BashSpiralGuardMiddleware
from bullseye_copilot.llm.workflows.copilot.tools.bullseye_mcp import ALLOWED_TOOLS
from bullseye_copilot.llm.prompts.loader import build_system_prompt
from bullseye_copilot.llm.workflows.copilot.tools.bash import make_bash_tool
from bullseye_copilot.llm.workflows.copilot.tools.files import make_file_tools
from bullseye_copilot.llm.workflows.copilot.tools.web import make_web_tools

# In-process conversation memory shared across turns. For production swap for a
# persistent checkpointer (langgraph-checkpoint-sqlite / -postgres) so threads
# survive restarts — see README.
CHECKPOINTER = MemorySaver()


def build_agent(
    *,
    bullseye_tools: list[BaseTool],
    workdir: Path,
    user: dict | None,
    model_alias: str | None,
    effort: str | None,
    checkpointer=CHECKPOINTER,
):
    """Build a compiled ReAct agent for this turn. `bullseye_tools` come from the
    live MCP session (see tools/bullseye_mcp.py); the rest are workspace-local."""
    file_tools = make_file_tools(workdir, read_roots=[KNOWLEDGE_DIR])
    tools: list[BaseTool] = [
        *bullseye_tools,
        *file_tools,
        make_bash_tool(workdir),
        *make_web_tools(),
    ]

    middleware = []

    # Clear stale tool outputs (cost #3): the heaviest input is tool-result data
    # accumulating across the loop. Past the trigger, older outputs become a
    # "[cleared]" placeholder (most recent CONTEXT_EDIT_KEEP kept). Cheap (no LLM)
    # and usually keeps a turn under the summarization trigger entirely.
    #
    # We exclude only the Bullseye data tools from clearing: their results are
    # small (a ./data pointer) yet expensive to reproduce — clearing them made the
    # agent re-fetch and loop. Everything else is fair game, and `clear_tool_inputs`
    # also drops the bulky *arguments* — most importantly each write_file's full
    # HTML, which otherwise lingers in context and inflates cache cost. Safe because
    # the artifact is on disk; edit_file re-reads it fresh.
    if ENABLE_CONTEXT_EDITING:
        preserve = tuple(sorted(ALLOWED_TOOLS))
        middleware.append(
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=CONTEXT_EDIT_TRIGGER_TOKENS,
                        keep=CONTEXT_EDIT_KEEP,
                        clear_tool_inputs=True,
                        exclude_tools=preserve,
                    )
                ]
            )
        )

    # Hard cap on full artifact rewrites (cost #4). The write-once prompt rule is
    # not reliably obeyed on complex artifacts, so block excess write_file calls
    # and steer the model to Edit instead. "continue" keeps the turn alive (other
    # tools still run); the model just can't keep regenerating the whole document.
    if WRITE_FILE_RUN_LIMIT > 0:
        middleware.append(
            ToolCallLimitMiddleware(
                tool_name="write_file",
                run_limit=WRITE_FILE_RUN_LIMIT,
                exit_behavior="continue",
            )
        )

    # Bash-spiral backstop (step-budget #5). Unlike write_file we don't hard-cap
    # bash — heavy turns legitimately need several calls. Instead, after a run of
    # consecutive bash-only steps, inject a reminder steering the model to
    # consolidate into one script (or finish the artifact) rather than keep
    # iterating. The prompt asks for this too; this enforces it on models that
    # don't plan (e.g. Claude at low effort, with no thinking budget).
    if BASH_SPIRAL_THRESHOLD > 0:
        middleware.append(
            BashSpiralGuardMiddleware(
                threshold=BASH_SPIRAL_THRESHOLD,
                repeat=BASH_SPIRAL_REPEAT,
            )
        )

    # Bound history growth (cost #2): once the running history crosses the token
    # trigger, older turns are condensed by a cheap model while the most recent
    # messages stay verbatim. Runs before caching so the (now-shorter) message
    # tail is what reaches the model. No effect on our cache, which only tags the
    # stable system+tools prefix, not the messages.
    if ENABLE_SUMMARIZATION:
        middleware.append(
            SummarizationMiddleware(
                model=build_model(SUMMARY_MODEL, "low"),
                trigger=("tokens", SUMMARY_TRIGGER_TOKENS),
                keep=("messages", SUMMARY_KEEP_MESSAGES),
            )
        )

    # Prompt caching (cost #1): tags the system prompt's last block and the tool
    # set with cache_control so that large, static prefix is re-read from cache
    # (~90% cheaper) every step and every follow-up turn. Anthropic-only — for
    # OpenAI models this middleware is inert (it warns and skips), and OpenAI's
    # automatic prompt caching applies instead, so we only add it for Claude.
    if provider_of(model_alias) == "anthropic":
        middleware.append(AnthropicPromptCachingMiddleware(ttl="5m"))

    if ENABLE_HITL:
        from bullseye_copilot.llm.workflows.copilot.middleware import (
            confirm_before_write_middleware,
        )

        middleware.append(confirm_before_write_middleware())

    return create_agent(
        model=build_model(model_alias, effort),
        tools=tools,
        system_prompt=build_system_prompt(user),
        checkpointer=checkpointer,
        middleware=middleware,
    )
