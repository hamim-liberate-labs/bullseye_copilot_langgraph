"""
Confirm-before-write — the "ask before changing data" safety rule.

Two ways to enforce it:

1. **Prose confirmation (default, matches the Agent-SDK build).** The system
   prompt already requires the assistant to state the change in plain language
   and wait for the user to say yes before calling `next_steps_write`. This keeps
   the one-shot streaming turn loop intact and needs no frontend changes.

2. **Enforced interrupt (migration plan, Phase 6 — opt-in via BULLSEYE_ENABLE_HITL).**
   `HumanInTheLoopMiddleware` hard-pauses the graph before `next_steps_write`,
   surfacing the pending call for approval. This is a genuine safety upgrade, but
   it requires a checkpointer (we have one) AND a frontend that can resume the
   thread with `Command(resume=...)`. The current frontend cannot, so it is OFF
   by default. Wire the resume path (Phases 6–7) before enabling.
"""

import logging

from langchain.agents.middleware import AgentMiddleware, HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, HumanMessage

log = logging.getLogger("copilot.middleware")


def confirm_before_write_middleware() -> HumanInTheLoopMiddleware:
    """Interrupt before the one write tool so a human approves the change."""
    return HumanInTheLoopMiddleware(
        interrupt_on={
            "next_steps_write": True,  # create / update / toggle / delete next steps
        }
    )


# Reminder injected when the bash-spiral backstop trips. Phrased as a direct
# course-correction the model reads right before its next step.
_BASH_SPIRAL_REMINDER = (
    "[system reminder] You have now run bash {count} times in a row. This is the "
    "debugging-spiral pattern that exhausts the step budget and returns unfinished "
    "work. STOP iterating with small commands. Read the most recent error in full, "
    "then either (a) write ONE ./scripts/*.py that does all remaining computation "
    "and run it once, or (b) if you already have the numbers you need, proceed "
    "straight to writing/finishing the artifact. Do not run bash again just to "
    "re-check, preview, or patch one line at a time."
)


def _consecutive_bash_steps(messages: list) -> int:
    """Count trailing model steps whose tool calls were *only* `bash`.

    Walks the history backward over AI messages (skipping the interleaved tool
    results). A step that called any non-bash tool, produced plain text, or a
    turn boundary (HumanMessage) ends the run — so this measures the current
    uninterrupted bash streak, not bash usage across the whole turn.
    """
    streak = 0
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            break  # turn boundary — stop counting
        if isinstance(msg, AIMessage):
            tool_calls = msg.tool_calls or []
            if tool_calls and all(tc["name"] == "bash" for tc in tool_calls):
                streak += 1
            else:
                break  # a non-bash (or text-only) step breaks the streak
    return streak


class BashSpiralGuardMiddleware(AgentMiddleware):
    """Inject a course-correcting reminder after a run of consecutive bash-only
    steps, without blocking the tool. See config.BASH_SPIRAL_THRESHOLD."""

    def __init__(self, *, threshold: int, repeat: int) -> None:
        super().__init__()
        self.threshold = threshold
        self.repeat = max(repeat, 1)

    def before_model(self, state, runtime):  # noqa: ANN001 - middleware signature
        streak = _consecutive_bash_steps(state["messages"])
        # Fire on the threshold, then again every `repeat` steps if it persists.
        if streak >= self.threshold and (streak - self.threshold) % self.repeat == 0:
            log.warning("bash-spiral guard fired at %d consecutive bash steps", streak)
            return {
                "messages": [HumanMessage(content=_BASH_SPIRAL_REMINDER.format(count=streak))]
            }
        return None
