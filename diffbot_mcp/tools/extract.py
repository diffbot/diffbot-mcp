from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError

from ..api import request, resolve_token
from ..app import mcp

EXTRACT_BASE = "https://api.diffbot.com/v3"
PageType = Literal["article", "product", "discussion", "image", "video", "list", "event", "job", "faq"]

DESCRIPTION = (
    "Fetches a URL live and extracts it into markdown or structured JSON, classifying the page type. Use when a "
    "search_web 'url:<URL>' lookup misses, when the whole document is needed rather than matching chunks, or when "
    "the page's current state (prices, status, versions) is the question. Takes 1-10 seconds."
)


def normalize_url(url: str) -> str:
    url = url.strip()
    return url if url.startswith("http") else f"https://{url}"


@mcp.tool(name="extract", description=DESCRIPTION)
async def extract(
    url: Annotated[str, "Page URL; https:// added if missing"],
    page_type: Annotated[Optional[PageType], "Force a page type; default auto"] = None,
    format: Annotated[Literal["markdown", "json"], "'json' for the structured page record"] = "markdown",
) -> dict:
    params = {"token": resolve_token(), "url": normalize_url(url), "timeout": 30000}
    if format == "markdown":
        params["mode"] = "llm"

    data = await request(f"{EXTRACT_BASE}/{page_type or 'analyze'}", params=params)
    # the API reports a failed extraction inside a 200 body
    if isinstance(data, dict) and "errorCode" in data:
        raise ToolError(f"Extraction error {data['errorCode']}: {data.get('error', '')}. The page may be behind a login, a bot wall, or a JavaScript app; try a specific page_type such as 'article'.")
    return data
