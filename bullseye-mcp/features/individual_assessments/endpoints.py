"""Individual Assessments (sessions) — HTTP/domain calls."""

import asyncio

from core.session import BullseyeSession
from core.helpers import as_list, strip_html


async def session_detail(s: BullseyeSession, session_id: int) -> dict:
    base = f"/api/v1/individual_assessments/{session_id}"
    # full detail + comments concurrently; comments 403 on drafts -> [].
    d, cd = await asyncio.gather(
        s.get(base),
        s.safe_get(f"{base}/comments"),
    )
    d = d if isinstance(d, dict) else {}

    # /{id} returns full detail; pull objectives wherever they live.
    objectives = as_list(d.get("scoring_data") or {}, "objectives") or \
        as_list(d, "objectives")
    objectives = [
        {
            "name": o.get("name"),
            "score": (o.get("mastery_score") or {}).get("score") if isinstance(o, dict) else None,
            "notes": strip_html((o.get("mastery_score") or {}).get("notes")) if isinstance(o, dict) else None,
        }
        for o in objectives if isinstance(o, dict)
    ]

    return {
        "session_id": session_id,
        "title": d.get("session_name") or d.get("title"),
        "date": d.get("scheduled_at") or d.get("date"),
        "draft": d.get("draft"),
        "assessor": (d.get("assessor") or {}).get("name") if isinstance(d.get("assessor"), dict) else d.get("assessor"),
        "assessee": (d.get("assessee") or {}).get("name") if isinstance(d.get("assessee"), dict) else d.get("assessee"),
        "notes": strip_html(d.get("session_notes") or d.get("notes")),
        "objectives": objectives,
        "next_steps": as_list(d, "next_step_list", "next_steps"),
        "comments": as_list(cd, "comments"),
        "detail": d,
    }
