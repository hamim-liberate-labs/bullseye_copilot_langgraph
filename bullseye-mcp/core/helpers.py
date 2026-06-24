"""Pure parsing/formatting helpers — no HTTP, no session state."""

import re
import json
import logging
from html import unescape
from pathlib import Path
from typing import Any, Optional

from core.app import WORKDIR, OFFLOAD_MIN_BYTES

log = logging.getLogger("bullseye-mcp")

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: Any) -> Optional[str]:
    """HTML string (goal text, notes) -> clean single-spaced text. Non-strings pass through."""
    if not isinstance(value, str):
        return value
    text = _TAG_RE.sub(" ", value)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def clean_params(params: Optional[dict]) -> Optional[dict]:
    """Drop None-valued params so we don't send empty filters."""
    if not params:
        return None
    cleaned = {k: v for k, v in params.items() if v is not None}
    return cleaned or None


def as_list(data: Any, *keys: str) -> list:
    """First present list under `keys`, else [] (tolerates API shape drift)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def page_of(data: Any, *keys: str) -> tuple[list, dict]:
    """Split a paginated payload into (items, pagination block)."""
    items = as_list(data, *keys)
    pagination = data.get("pagination", {}) if isinstance(data, dict) else {}
    return items, pagination


def shape_of(value: Any, _depth: int = 0) -> Any:
    """A compact schema of `value`: field names + types, with arrays collapsed to
    {type, len, items-shape} so a 500-row list costs the shape of one row. Lets an
    agent see every available field and query the offloaded file selectively rather
    than reading it whole. (schema + sample is the standard large-data agent pattern)."""
    if isinstance(value, dict):
        if _depth >= 5:
            return "object"
        return {k: shape_of(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return {"type": "array", "len": 0}
        return {"type": "array", "len": len(value), "items": shape_of(value[0], _depth + 1)}
    if value is None:
        return "null"
    return type(value).__name__  # str / int / float / bool


def offload(name: str, payload: dict, summary: dict) -> dict:
    """Gateway mode: write `payload` to <workdir>/data/<name>.json and return a
    compact view (caller `summary` + the payload's `schema` + a file pointer),
    keeping bulk records out of the model's context. Small payloads are returned
    inline (not worth a file to read back), as is everything when BULLSEYE_WORKDIR
    is unset (interactive use)."""
    if not WORKDIR:
        return payload

    blob = json.dumps(payload, indent=1, ensure_ascii=False)
    if len(blob) < OFFLOAD_MIN_BYTES:
        return payload

    try:
        data_dir = Path(WORKDIR) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / f"{name}.json").write_text(blob, encoding="utf-8")
    except OSError as e:
        # Disk/permission failure: better to return the full payload inline than
        # to fail the tool with a dangling pointer.
        log.warning("offload of %s failed (%s) — returning inline", name, e)
        return payload

    return {
        **summary,
        "data_file": f"./data/{name}.json",
        "data_file_bytes": len(blob),
        "schema": shape_of(payload),
        "note": ("Full records in data_file. Use `schema` to see every field, then "
                 "query the file with code reading only what you need — do not read it whole."),
    }
