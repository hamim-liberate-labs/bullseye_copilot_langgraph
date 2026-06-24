"""
Next Steps tools — two action-dispatching tools over the whole feature:

  next_steps_read(action, …)   read-only GETs   (get | new_form | edit_data | list_completed)
  next_steps_write(action, …)  mutating writes  (create | update | delete | toggle_completion)

Splitting reads from writes keeps the read-only vs destructive annotation honest
(a read can never trip the confirm-before-write rule, a write always does) while
collapsing eight endpoints into two tools. Each `action` maps 1:1 to a function
in `endpoints.py`; params not relevant to the chosen action are simply unused.
"""

from typing import Literal, Optional

from fastmcp.exceptions import ToolError

from core.app import mcp
from core.annotations import DESTRUCTIVE, READ_ONLY
from core.session import session

from . import endpoints


def _require(action: str, **named) -> None:
    """Raise a clear ToolError naming the params the chosen action needs but lacks."""
    missing = [name for name, value in named.items() if value is None]
    if missing:
        raise ToolError(
            f"next_steps action={action!r} requires: {', '.join(missing)}."
        )


@mcp.tool(tags={"next_steps", "read"}, annotations=READ_ONLY)
async def next_steps_read(
    action: Literal["get", "new_form", "edit_data", "list_completed"],
    completion_location_type: Optional[str] = None,
    completion_location_id: Optional[int] = None,
    next_step_id: Optional[int] = None,
) -> dict:
    """
    Read next-step data. `action` selects what to fetch; all actions need the
    completion location (`completion_location_type` + `completion_location_id`,
    e.g. 'Session'/session_id or 'Student'/person_id):

      - "get"            full detail for one next step (needs `next_step_id`):
                         description, due date, owner, completion info.
      - "new_form"       options for creating a next step here: valid owners,
                         objectives, learning resources, plus feature flags.
      - "edit_data"      one next step's current values + the same option lists,
                         for building an update (needs `next_step_id`).
      - "list_completed" completed next steps for the location (dated, with source);
                         `completion_location_type` defaults to 'Session'.
    """
    s = session()
    if action == "list_completed":
        _require(action, completion_location_id=completion_location_id)
        return await endpoints.completed_next_steps(
            s, completion_location_id, completion_location_type or "Session")

    _require(action, completion_location_type=completion_location_type,
             completion_location_id=completion_location_id)
    if action == "new_form":
        return await endpoints.new_next_step_form(
            s, completion_location_type, completion_location_id)

    _require(action, next_step_id=next_step_id)
    if action == "get":
        return await endpoints.next_step_detail(
            s, next_step_id, completion_location_type, completion_location_id)
    # action == "edit_data"
    return await endpoints.edit_next_step_data(
        s, next_step_id, completion_location_type, completion_location_id)


@mcp.tool(tags={"next_steps", "write"}, annotations=DESTRUCTIVE)
async def next_steps_write(
    action: Literal["create", "update", "delete", "toggle_completion"],
    completion_location_type: str,
    completion_location_id: int,
    next_step_id: Optional[int] = None,
    title: Optional[str] = None,
    owner_ids: Optional[list[int]] = None,
    creation_location_type: Optional[str] = None,
    creation_location_id: Optional[int] = None,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    owner_id: Optional[int] = None,
    objective_ids: Optional[list[int]] = None,
    learning_resource_ids: Optional[list[int]] = None,
    media_attributes: Optional[list[dict]] = None,
    linked_urls_attributes: Optional[list[dict]] = None,
    locked: Optional[bool] = None,
) -> dict:
    """
    Create, update, delete, or toggle a next step. **Changes real Bullseye data —
    confirm with the user before calling, and especially for `delete` (irreversible).**
    `completion_location_type`/`completion_location_id` (the placement) are always
    required. `action` selects the operation and which extra fields apply:

      - "create"            new action item. Needs `title`, `owner_ids` (owners are
                            assigned from this list — do NOT pass `owner_id`, an
                            update-only field, or the API creates a duplicate),
                            `creation_location_type`, `creation_location_id`. Optional:
                            `description`, `due_date` (YYYY-MM-DD), `objective_ids`,
                            `learning_resource_ids`, `media_attributes`,
                            `linked_urls_attributes`, `locked`.
      - "update"            change a next step (needs `next_step_id`). Send only the
                            fields to change: `title`, `description`, `due_date`,
                            `owner_id`, `locked`, `objective_ids`,
                            `learning_resource_ids`, `media_attributes`,
                            `linked_urls_attributes`. Use action="edit_data" first.
      - "delete"            permanently remove a next step (needs `next_step_id`).
      - "toggle_completion" flip complete/incomplete (needs `next_step_id`).

    Returns the updated `next_step_list` (and `next_step_details` for toggle).
    """
    s = session()
    if action == "create":
        _require(action, title=title, owner_ids=owner_ids,
                 creation_location_type=creation_location_type,
                 creation_location_id=creation_location_id)
        return await endpoints.create_next_step(
            s, completion_location_type, completion_location_id, title, owner_ids,
            creation_location_type, creation_location_id, description, due_date,
            objective_ids, learning_resource_ids, media_attributes,
            linked_urls_attributes, locked)

    _require(action, next_step_id=next_step_id)
    if action == "update":
        return await endpoints.update_next_step(
            s, next_step_id, completion_location_type, completion_location_id,
            title, description, due_date, owner_id, locked, objective_ids,
            learning_resource_ids, media_attributes, linked_urls_attributes)
    if action == "delete":
        return await endpoints.delete_next_step(
            s, next_step_id, completion_location_type, completion_location_id)
    # action == "toggle_completion"
    return await endpoints.toggle_next_step_completion(
        s, next_step_id, completion_location_type, completion_location_id)
