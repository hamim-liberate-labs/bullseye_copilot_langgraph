"""
People (learner profile) tools — goals, records, objective detail.

`person_id` is the LEARNER PROFILE id — the person being observed/coached (the
assessee), NOT the coach running the session. It is the same value as `student_id`
(e.g. dashboard `current_staff.student_id` is the signed-in staff member's own
learner profile id, for self-queries as the observed person). So these tools
return data ABOUT the learner: sessions conducted ON them, objectives scored FOR
them, notes written ABOUT them — never sessions/notes they authored as an observer.
"""

from typing import Literal

from core.app import mcp
from core.annotations import READ_ONLY
from core.session import session
from core.helpers import offload

from . import endpoints
from .models import ActiveGoal, GoalHistory, ObjectiveDetail


@mcp.tool(tags={"people", "read"}, annotations=READ_ONLY)
async def get_active_goal(person_id: int) -> ActiveGoal:
    """
    The learner's current coaching goal (`person_id` = learner profile id, same as
    `student_id`): cleaned text (`goal`), the raw HTML (`goal_html`) for rendering,
    and any linked objectives.
    """
    return await endpoints.active_goal(session(), person_id)


@mcp.tool(tags={"people", "read"}, annotations=READ_ONLY)
async def get_goal_history(person_id: int) -> GoalHistory:
    """
    The learner's coaching-goal history, newest first (`person_id` = learner
    profile id). Each entry includes the raw `goal` HTML plus a cleaned `goal_text`,
    objective names, date, and author.
    """
    return await endpoints.goal_history(session(), person_id)


@mcp.tool(tags={"people", "read"}, annotations=READ_ONLY)
async def get_person_records(person_id: int,
                             record_type: Literal["sessions", "objectives", "notes", "checklist_items"],
                             page: int = 1, per_page: int = 20,
                             search_value: str = None) -> dict:
    """
    Paginated records for a LEARNER (`person_id` = learner profile id, same as
    `student_id` — the observed person, not the coach). `record_type` selects what
    to return ABOUT that learner:
      - "sessions"        — sessions conducted ON them (they are the assessee, not
                            the observer): id, title, date, score_percentages, draft
      - "objectives"      — objectives scored FOR them: name, component, last score,
                            observer, up to 5 recent scores
      - "notes"           — session notes written ABOUT them: date, observer,
                            context, raw + cleaned note text
      - "checklist_items" — checklist items recorded for them: name, header, linked
                            objective, yes/no counts and distribution %
    Newest first; page with `page`/`per_page`; filter with `search_value`. For one
    objective's full score history use get_objective_detail instead, and call
    get_session for full detail on any session row. In gateway mode the page is
    offloaded with a schema + preview.
    """
    payload = await endpoints.person_records(session(), person_id, record_type,
                                             page, per_page, search_value)
    return offload(
        f"person_{person_id}_{record_type}_p{page}",
        payload,
        {"person_id": person_id, "record_type": record_type,
         "count": payload["count"], "pagination": payload["pagination"],
         "preview": payload["records"][:3]},
    )


@mcp.tool(tags={"people", "read"}, annotations=READ_ONLY)
async def get_objective_detail(person_id: int, objective_id: int,
                                page: int = 1, per_page: int = 20,
                                search_value: str = None) -> ObjectiveDetail:
    """
    Full detail for one objective scored for a learner (`person_id` = learner
    profile id): objective definition, linked learning resources, score band, and
    the complete score history (session date, observer, session notes, objective
    notes). Paginated. Use `search_value` to filter scores by observer name or note
    content.
    """
    return await endpoints.objective_detail(session(), person_id, objective_id,
                                             page, per_page, search_value)
