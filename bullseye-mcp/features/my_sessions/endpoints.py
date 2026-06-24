"""My Sessions — HTTP/domain calls."""

from typing import Optional

from core.session import BullseyeSession
from core.helpers import clean_params, page_of


async def list_sessions(s: BullseyeSession, start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        search_value: Optional[str] = None,
                        page: int = 1, per_page: int = 20,
                        order_by: str = "date", direction: str = "desc",
                        with_filter_options: Optional[bool] = None) -> dict:
    # Paginated (~20/page, newest first). with_filter_options=True attaches a
    # filter_options block (templates, classrooms, tags, statuses).
    filters = {
        "start_date": start_date, "end_date": end_date, "search_value": search_value,
        "page": page, "per_page": per_page, "order_by": order_by, "direction": direction,
        "with_filter_options": with_filter_options,
    }
    d = await s.get("/api/v1/my_sessions", params=clean_params(filters))
    sessions, pagination = page_of(d, "sessions")
    filter_options = d.get("filter_options", {}) if isinstance(d, dict) else {}
    applied = clean_params({"start_date": start_date, "end_date": end_date,
                            "search_value": search_value, "order_by": order_by,
                            "direction": direction})
    return {"sessions": sessions, "count": len(sessions),
            "pagination": pagination,
            "filter_options": filter_options,
            "filters": applied or {}}
