"""
Per-conversation artifact workspace: the file-tool isolation boundary.

A private folder per chat_id, the help-center snapshot surfaced as ./help, plus
the artifact-marker extraction and scanning the frontend's side panel depends on.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bullseye_copilot.core.config import ARTIFACTS_ROOT, KNOWLEDGE_DIR

log = logging.getLogger("copilot.workspace")

# chat_id / thread path-segment guard — only safe slug characters.
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_ARTIFACT_MARKER_RE = re.compile(r"<artifact>\s*(.*?)\s*</artifact>", re.DOTALL)


def ensure_workspace(chat_id: str) -> Path:
    """Create (idempotently) the chat's workspace and link the help snapshot in
    as ./help so the agent reaches it with the same ./-relative access it uses
    for ./data — no external paths in its mental model."""
    workdir = ARTIFACTS_ROOT / chat_id
    workdir.mkdir(parents=True, exist_ok=True)
    help_link = workdir / "help"
    if KNOWLEDGE_DIR.is_dir() and not help_link.exists():
        try:
            help_link.symlink_to(KNOWLEDGE_DIR, target_is_directory=True)
        except OSError:
            # On Windows, symlinks may require privilege; fall back silently.
            # Help reads still work via the file tools' extra read-root grant.
            log.warning("could not link help knowledge base into %s", workdir)
    return workdir


def extract_artifact_marker(
    reply: str, chat_id: str, workdir: Path
) -> tuple[str, dict | None]:
    """Pull the model's <artifact>path</artifact> intent marker out of the reply.

    The marker is intent only — never trusted as a path. We reduce it to a thread
    slug, validate it, and check the artifact actually exists in this chat's
    workspace. Returns (cleaned_reply, active_artifact | None).
    """
    m = _ARTIFACT_MARKER_RE.search(reply)
    if not m:
        return reply, None
    cleaned = _ARTIFACT_MARKER_RE.sub("", reply).strip()

    raw = m.group(1).strip()
    if raw.startswith(str(workdir)):
        raw = raw[len(str(workdir)):]
    raw = raw.lstrip("/").removeprefix("./")
    thread = raw.split("/")[0] if raw else ""

    if not ID_RE.match(thread) or not (workdir / thread / "artifact.html").is_file():
        return cleaned, None
    return cleaned, {"thread": thread, "url": f"/api/artifacts/{chat_id}/{thread}"}


def scan_artifacts(chat_id: str, workdir: Path) -> list[dict]:
    artifacts = []
    for f in sorted(workdir.glob("*/artifact.html")):
        thread = f.parent.name
        artifacts.append(
            {
                "thread": thread,
                "url": f"/api/artifacts/{chat_id}/{thread}",
                "updated_at": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return artifacts
