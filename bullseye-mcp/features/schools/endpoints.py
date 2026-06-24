"""Schools — HTTP/domain calls."""

from core.session import BullseyeSession
from core.helpers import as_list


async def schools(s: BullseyeSession) -> dict:
    data = await s.get("/api/v1/schools", needs_school=False)
    schools = as_list(data, "schools")
    if s.school_id is None and schools:
        s.school_id = schools[0]["id"]
    return {"schools": schools, "active_school_id": s.school_id, "count": len(schools)}
