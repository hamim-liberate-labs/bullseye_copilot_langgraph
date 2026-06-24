"""My Sessions tool."""

from core.app import mcp
from core.annotations import READ_ONLY
from core.session import session
from core.helpers import offload

from . import endpoints


@mcp.tool(tags={"my_sessions", "read"}, annotations=READ_ONLY)
async def list_sessions(start_date: str = None, end_date: str = None,
                        search_value: str = None, page: int = 1,
                        per_page: int = 20, order_by: str = "date",
                        direction: str = "desc",
                        with_filter_options: bool = None) -> dict:
    """
    Return the user's sessions as lean rows. Optionally filter by an ISO
    (YYYY-MM-DD) date window and/or `search_value` text. Control the sort with
    `order_by` (e.g. 'date') and `direction` ('asc'/'desc'). Set
    `with_filter_options=True` to also get a `filter_options` block (session
    templates, classrooms, tags, statuses, session content) for building filter
    UIs. The list is paginated (~20/page); read `pagination.total_pages` and
    request further `page`s to cover everything. In gateway mode the page is
    offloaded to a data file and a count, the pagination block, and a 3-row
    preview are returned (see `offload`).
    """
    payload = await endpoints.list_sessions(session(), start_date=start_date, end_date=end_date,
                                             search_value=search_value, page=page,
                                             per_page=per_page, order_by=order_by,
                                             direction=direction,
                                             with_filter_options=with_filter_options)
    sessions = payload["sessions"]
    preview_keys = (
        "id", "title", "second_title", "date", "session_type", "draft", "comments_count",
    )
    summary = {
        "count": payload["count"],
        "pagination": payload["pagination"],
        "filters": payload["filters"],
        "preview": [
            {k: v for k, v in s.items() if k in preview_keys} for s in sessions[:3]
        ],
    }
    # Only surface filter_options when the caller asked for them and the API returned a block.
    if payload.get("filter_options"):
        summary["filter_options"] = payload["filter_options"]
    return offload(f"sessions_p{page}", payload, summary)
