"""Next Steps — HTTP/domain calls (reads + writes)."""

from typing import Optional

from fastmcp.exceptions import ToolError

from core.session import BullseyeSession
from core.helpers import as_list, clean_params, strip_html


def _location_params(completion_location_type: str,
                     completion_location_id: int) -> dict:
    # The /new, /{id}, and /{id}/edit GETs all 400 without both; they identify the
    # placement whose options/detail to return.
    return {"completion_location_type": completion_location_type,
            "completion_location_id": completion_location_id}


async def completed_next_steps(s: BullseyeSession, completion_location_id: int,
                               completion_location_type: str = "Session") -> dict:
    # Both params required (a bare call 400s); guard for a clean error.
    if not (completion_location_type and completion_location_id):
        raise ToolError(
            "completed_next_steps requires completion_location_type and "
            "completion_location_id (e.g. type='Session', id=<session_id>)."
        )
    params = {"completion_location_type": completion_location_type,
              "completion_location_id": completion_location_id}
    d = await s.get("/api/v1/next_steps/completed_next_steps_history", params=params)
    completed = as_list(d, "completed_next_steps", "next_steps", "history")
    # Mirror get/edit: keep raw `description` (HTML) and add a clean `description_text`.
    for item in completed:
        if isinstance(item, dict) and "description" in item:
            item["description_text"] = strip_html(item.get("description"))
    return {"completed": completed}


async def new_next_step_form(s: BullseyeSession, completion_location_type: str,
                             completion_location_id: int) -> dict:
    """Form data for creating a next step at a location: the valid owners,
    objectives, and learning resources to pick ids from, plus feature flags."""
    d = await s.get("/api/v1/next_steps/new",
                    params=_location_params(completion_location_type, completion_location_id))
    d = d if isinstance(d, dict) else {}
    return {
        "resource_center_enabled": d.get("resource_center_enabled"),
        "all_learning_resources": as_list(d, "all_learning_resources"),
        "show_owner_options": d.get("show_owner_options"),
        "show_classroom_options": d.get("show_classroom_options"),
        "owner_options": as_list(d, "owner_options"),
        "all_mastery_objectives": as_list(d, "all_mastery_objectives"),
        "school_next_step_locking": d.get("school_next_step_locking"),
    }


async def next_step_detail(s: BullseyeSession, next_step_id: int,
                           completion_location_type: str,
                           completion_location_id: int) -> dict:
    """Full detail for one next step at a placement (description, due date, owner,
    resource center, completion_info if done)."""
    d = await s.get(f"/api/v1/next_steps/{next_step_id}",
                    params=_location_params(completion_location_type, completion_location_id))
    d = d if isinstance(d, dict) else {}
    details = d.get("next_step_details") if isinstance(d.get("next_step_details"), dict) else {}
    if "description" in details:
        details["description_text"] = strip_html(details.get("description"))
    return {"next_step_id": next_step_id, "next_step_details": details}


async def edit_next_step_data(s: BullseyeSession, next_step_id: int,
                              completion_location_type: str,
                              completion_location_id: int) -> dict:
    """Edit form data for one next step: its current values (`next_step_data`) plus
    the same option lists as the create form, for building an update payload."""
    d = await s.get(f"/api/v1/next_steps/{next_step_id}/edit",
                    params=_location_params(completion_location_type, completion_location_id))
    d = d if isinstance(d, dict) else {}
    ns = d.get("next_step_data") if isinstance(d.get("next_step_data"), dict) else {}
    if "description" in ns:
        ns["description_text"] = strip_html(ns.get("description"))
    return {
        "next_step_data": ns,
        "resource_center_enabled": d.get("resource_center_enabled"),
        "all_learning_resources": as_list(d, "all_learning_resources"),
        "show_owner_options": d.get("show_owner_options"),
        "owner_options": as_list(d, "owner_options"),
        "all_mastery_objectives": as_list(d, "all_mastery_objectives"),
    }


async def create_next_step(s: BullseyeSession, completion_location_type: str,
                           completion_location_id: int, title: str,
                           owner_ids: list[int],
                           creation_location_type: str,
                           creation_location_id: int,
                           description: Optional[str] = None,
                           due_date: Optional[str] = None,
                           objective_ids: Optional[list[int]] = None,
                           learning_resource_ids: Optional[list[int]] = None,
                           media_attributes: Optional[list[dict]] = None,
                           linked_urls_attributes: Optional[list[dict]] = None,
                           locked: Optional[bool] = None) -> dict:
    # Owners come solely from `owner_ids` (one next step per owner). Do NOT also
    # send the singular `owner_id` (an update-only field): the API unions the two,
    # so an overlapping owner_id creates a duplicate next step.
    next_step = clean_params({
        "title": title, "description": description, "due_date": due_date,
        "creation_location_type": creation_location_type,
        "creation_location_id": creation_location_id,
        "owner_ids": owner_ids,
        "objective_ids": objective_ids,
        "learning_resource_ids": learning_resource_ids,
        "media_attributes": media_attributes,
        "linked_urls_attributes": linked_urls_attributes,
        "locked": locked,
    })
    body = {"completion_location_type": completion_location_type,
            "completion_location_id": completion_location_id,
            "next_step": next_step}
    d = await s.write("POST", "/api/v1/next_steps", json_body=body)
    data = d.get("data") or {}
    return {"message": d.get("message"),
            "next_step_list": as_list(data, "next_step_list"),
            "failed_next_step_owners": data.get("failed_next_step_owners")}


async def update_next_step(s: BullseyeSession, next_step_id: int,
                           completion_location_type: str,
                           completion_location_id: int,
                           title: Optional[str] = None,
                           description: Optional[str] = None,
                           due_date: Optional[str] = None,
                           owner_id: Optional[int] = None,
                           locked: Optional[bool] = None,
                           objective_ids: Optional[list[int]] = None,
                           learning_resource_ids: Optional[list[int]] = None,
                           media_attributes: Optional[list[dict]] = None,
                           linked_urls_attributes: Optional[list[dict]] = None) -> dict:
    # PATCH carries only changed `next_step` fields (no creation_location / owner_ids,
    # unlike create). Both completion-location params identify the placement.
    next_step = clean_params({
        "title": title, "description": description, "due_date": due_date,
        "owner_id": owner_id, "locked": locked,
        "objective_ids": objective_ids,
        "learning_resource_ids": learning_resource_ids,
        "media_attributes": media_attributes,
        "linked_urls_attributes": linked_urls_attributes,
    })
    body = {"completion_location_type": completion_location_type,
            "completion_location_id": completion_location_id,
            "next_step": next_step or {}}
    d = await s.write("PATCH", f"/api/v1/next_steps/{next_step_id}", json_body=body)
    data = d.get("data") or {}
    return {"message": d.get("message"),
            "next_step_list": as_list(data, "next_step_list")}


async def delete_next_step(s: BullseyeSession, next_step_id: int,
                           completion_location_type: str,
                           completion_location_id: int) -> dict:
    # DELETE takes the completion-location as query params (which placement to
    # remove); school_id is injected like every write. Returns the updated list.
    params = _location_params(completion_location_type, completion_location_id)
    d = await s.write("DELETE", f"/api/v1/next_steps/{next_step_id}", params=params)
    data = d.get("data") or {}
    return {"message": d.get("message"),
            "next_step_list": as_list(data, "next_step_list")}


async def toggle_next_step_completion(s: BullseyeSession, next_step_id: int,
                                      completion_location_type: str,
                                      completion_location_id: int) -> dict:
    # Both completion-location params required — they identify which placement to flip.
    body = {"completion_location_type": completion_location_type,
            "completion_location_id": completion_location_id}
    d = await s.write(
        "PATCH", f"/api/v1/next_steps/{next_step_id}/completion_toggle",
        json_body=body)
    data = d.get("data") or {}
    return {"message": d.get("message"),
            "next_step_list": as_list(data, "next_step_list"),
            "next_step_details": data.get("next_step_details") or {}}
