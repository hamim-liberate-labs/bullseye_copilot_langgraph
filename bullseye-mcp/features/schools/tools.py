"""Schools tools — school context + active-school selection (local state)."""

from core.app import mcp
from core.annotations import LOCAL_STATE, READ_ONLY
from core.session import session

from . import endpoints
from .models import SchoolContext


@mcp.tool(tags={"schools", "read"}, annotations=READ_ONLY)
async def get_school_context() -> SchoolContext:
    """
    Return the schools accessible to the authenticated user. Defaults the active
    school to the first if none is set; use set_active_school to choose another.
    """
    return await endpoints.schools(session())


@mcp.tool(tags={"schools"}, annotations=LOCAL_STATE)
async def set_active_school(school_id: int) -> SchoolContext:
    """
    Set the active school used by downstream tools. Required when the user belongs
    to more than one school and the wrong one was auto-selected.
    """
    s = session()
    s.school_id = school_id
    return {"schools": [], "active_school_id": school_id, "count": 0}
