"""Dashboard — HTTP/domain calls."""

from core.session import BullseyeSession
from core.helpers import as_list, strip_html


async def dashboard(s: BullseyeSession) -> dict:
    # Staff home overview: active goal, open next steps, recent sessions, school
    # context. Goal HTML fields are cleaned to `*_text` alongside the raw values.
    d = await s.get("/api/v1/dashboards")
    d = d if isinstance(d, dict) else {}
    goal = d.get("active_goal_data") or {}
    if isinstance(goal, dict):
        for k in ("active_goal", "draft_active_goal", "active_goal_description"):
            if k in goal:
                goal[f"{k}_text"] = strip_html(goal.get(k))
    return {
        "active_goal_data": goal if isinstance(goal, dict) else {},
        "next_step_list": as_list(d, "next_step_list"),
        "recent_session_data": as_list(d, "recent_session_data"),
        "current_school_specific_data": d.get("current_school_specific_data") or {},
    }
