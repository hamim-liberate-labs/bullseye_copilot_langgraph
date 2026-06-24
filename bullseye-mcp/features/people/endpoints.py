"""People (learner profile) — HTTP/domain calls.

`person_id` is the learner profile id (the observed/coached person, == student_id),
so everything here is data ABOUT that learner."""

from typing import Optional

from fastmcp.exceptions import ToolError

from core.session import BullseyeSession
from core.helpers import as_list, clean_params, page_of, strip_html

# The four paginated learner record lists share one access pattern: the path
# segment and the response list key both equal the record_type.
PERSON_RECORD_TYPES = ("sessions", "objectives", "notes", "checklist_items")


def _page_params(page: int, per_page: int, search_value: Optional[str]) -> Optional[dict]:
    return clean_params({"page": page, "per_page": per_page, "search_value": search_value})


async def active_goal(s: BullseyeSession, person_id: int) -> dict:
    d = await s.get(f"/api/v1/people/{person_id}/get_active_goal")
    d = d if isinstance(d, dict) else {"goal": d}
    goal_html = d.get("active_goal") or d.get("goal")
    return {
        "person_id": person_id,
        "goal": strip_html(goal_html),
        "goal_html": goal_html,
        "objectives": as_list(d, "active_goal_objectives", "objectives"),
    }


async def goal_history(s: BullseyeSession, person_id: int) -> dict:
    d = await s.get(f"/api/v1/people/{person_id}/active_goal_history")
    goals = as_list(d, "historical_goals")
    for g in goals:
        if isinstance(g, dict) and "goal" in g:
            g["goal_text"] = strip_html(g.get("goal"))
    return {"goals": goals}


async def person_records(s: BullseyeSession, person_id: int, record_type: str,
                         page: int = 1, per_page: int = 20,
                         search_value: Optional[str] = None) -> dict:
    """Paginated learner records of one type (sessions / objectives / notes /
    checklist_items) — data ABOUT the learner, not what they authored."""
    if record_type not in PERSON_RECORD_TYPES:
        raise ToolError(
            f"unknown record_type {record_type!r}; expected one of {list(PERSON_RECORD_TYPES)}"
        )
    d = await s.get(f"/api/v1/people/{person_id}/{record_type}",
                    params=_page_params(page, per_page, search_value))
    records, pagination = page_of(d, record_type)
    if record_type == "notes":
        for n in records:
            if isinstance(n, dict) and "notes" in n:
                n["notes_text"] = strip_html(n.get("notes"))
    return {"person_id": person_id, "record_type": record_type,
            "records": records, "count": len(records), "pagination": pagination}


async def objective_detail(s: BullseyeSession, person_id: int, objective_id: int,
                           page: int = 1, per_page: int = 20,
                           search_value: Optional[str] = None) -> dict:
    d = await s.get(f"/api/v1/people/{person_id}/objectives/{objective_id}",
                    params=_page_params(page, per_page, search_value))
    d = d if isinstance(d, dict) else {}
    scores = as_list(d, "scores")
    for sc in scores:
        if isinstance(sc, dict):
            if "session_notes" in sc:
                sc["session_notes_text"] = strip_html(sc.get("session_notes"))
            if "objective_notes" in sc:
                sc["objective_notes_text"] = strip_html(sc.get("objective_notes"))
    return {"person_id": person_id, "objective_id": objective_id,
            "objective": d.get("objective", {}),
            "scores": scores,
            "learning_resources": as_list(d, "learning_resources"),
            "score_band": d.get("score_band"),
            "pagination": d.get("pagination", {})}
