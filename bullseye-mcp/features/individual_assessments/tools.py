"""Individual Assessments (sessions) tool."""

from core.app import mcp
from core.annotations import READ_ONLY
from core.session import session
from core.helpers import offload

from . import endpoints


@mcp.tool(tags={"individual_assessments", "read"}, annotations=READ_ONLY)
async def get_session(session_id: int) -> dict:
    """
    Full detail for one session (title, date, notes, objectives, next steps, and
    the raw payload under `detail`) plus its comments, fetched concurrently.
    `next_steps` carries the session's pending/owned action items. Comments are
    empty for draft sessions. In gateway mode the full payload is offloaded to a
    data file and a compact summary returned.
    """
    payload = await endpoints.session_detail(session(), session_id)
    objectives = payload["objectives"]
    return offload(
        f"session_{session_id}",
        payload,
        {
            "session_id": session_id,
            "title": payload["title"],
            "date": payload["date"],
            "assessor": payload["assessor"],
            "assessee": payload["assessee"],
            "scored_objectives": sum(1 for o in objectives if o.get("score") is not None),
            "objectives": len(objectives),
            "next_steps": len(payload["next_steps"]),
            "comments": len(payload["comments"]),
        },
    )
