"""
Open-web tools: `web_fetch` (always available) and `web_search` (Tavily, only if
TAVILY_API_KEY is set). The system prompt confines these to *general* context —
Bullseye facts must always come from the Bullseye data tools, never the web.
"""

import logging
import os
import re

import httpx
from langchain_core.tools import StructuredTool

log = logging.getLogger("copilot.web")

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_MAX_FETCH_BYTES = 40_000


def _strip_html(html: str) -> str:
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _ANY_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


async def _web_fetch(url: str) -> str:
    """Fetch a web page and return its readable text (HTML tags stripped). Use for
    general external references — never for Bullseye data.

    Args:
        url: The absolute http(s) URL to fetch.
    """
    if not url.startswith(("http://", "https://")):
        return "ERROR: url must start with http:// or https://"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            r = await client.get(url, headers={"User-Agent": "BullseyeCopilot/1.0"})
    except httpx.HTTPError as e:
        return f"ERROR fetching {url}: {e}"
    if r.status_code >= 400:
        return f"ERROR: {url} returned {r.status_code}"
    return _strip_html(r.text)[:_MAX_FETCH_BYTES]


def make_web_tools() -> list[StructuredTool]:
    tools = [StructuredTool.from_function(coroutine=_web_fetch, name="web_fetch")]

    if os.getenv("TAVILY_API_KEY"):
        try:
            from langchain_tavily import TavilySearch

            tools.append(TavilySearch(max_results=5, name="web_search"))
        except ImportError:
            log.warning("TAVILY_API_KEY set but langchain-tavily not installed; "
                        "web_search disabled")
    return tools
