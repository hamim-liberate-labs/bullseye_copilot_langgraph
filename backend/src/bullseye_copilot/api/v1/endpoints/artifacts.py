"""Artifact serving: the HTML files the agent writes into per-chat workspaces,
rendered by the frontend's side panel in a sandboxed iframe."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from bullseye_copilot.core.config import ARTIFACTS_ROOT
from bullseye_copilot.utils.workspace import ID_RE

router = APIRouter()


@router.get("/api/artifacts/{chat_id}/{thread}")
async def get_artifact(chat_id: str, thread: str) -> FileResponse:
    if not (ID_RE.match(chat_id) and ID_RE.match(thread)):
        raise HTTPException(status_code=400, detail="invalid path")
    path = ARTIFACTS_ROOT / chat_id / thread / "artifact.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    # Agent-generated HTML is untrusted: the frontend renders it in a sandboxed
    # iframe; no-store so panel refreshes always pick up edits.
    return FileResponse(
        path, media_type="text/html", headers={"Cache-Control": "no-store"}
    )
