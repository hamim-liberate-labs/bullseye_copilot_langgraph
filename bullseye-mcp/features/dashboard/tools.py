"""Dashboard tool."""

from core.app import mcp
from core.annotations import READ_ONLY
from core.session import session

from . import endpoints
from .models import Dashboard


@mcp.tool(tags={"dashboard", "read"}, annotations=READ_ONLY)
async def get_dashboard() -> Dashboard:
    """
    The authenticated staff member's home dashboard in a single call: their active
    goal (raw HTML + cleaned `*_text`), the list of open/owned next steps, recent
    sessions (latest few, with objectives and score_percentages), and school
    context. `current_school_specific_data.current_staff.student_id` is the staff
    member's OWN learner profile id (same as `person_id`) — pass it to the
    person-scoped tools for self-queries (their data AS the observed learner, e.g.
    sessions conducted ON them, not sessions they ran). Scoped to the active
    school; takes no arguments. Best first call for "what should I focus on?" or a
    personal overview.
    """
    return await endpoints.dashboard(session())
