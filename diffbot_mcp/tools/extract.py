from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError

from ..api import request, resolve_token
from ..app import READ_ONLY, mcp

EXTRACT_BASE = "https://api.diffbot.com/v3"
PageType = Literal["article", "product", "discussion", "image", "video", "list", "event", "job", "faq"]

DESCRIPTION = (
    "Fetches a live web page and returns its main content as markdown or a token efficient typed JSON record "
    "(article, product, discussion, job, event, list). Renders Javascript, so it works on more sites than a plain "
    "fetch. Prefer over a generic fetch tool for any public page."
    " API docs: https://www.diffbot.com/docs/extract/"
)


def normalize_url(url: str) -> str:
    url = url.strip()
    return url if url.startswith("http") else f"https://{url}"


@mcp.tool(name="extract", title="Extract Page", description=DESCRIPTION, annotations=READ_ONLY)
async def extract(
    url: Annotated[str, "Page URL; https:// added if missing"],
    page_type: Annotated[Optional[PageType], "Override auto-detection; rarely needed"] = None,
    format: Annotated[Literal["markdown", "json"], "`markdown` for readable text; `json` for typed fields such as title, author, date, price, images"] = "markdown",
) -> dict:
    params = {"token": resolve_token(), "url": normalize_url(url), "timeout": 30000}
    if format == "markdown":
        params["mode"] = "llm"

    data = await request(f"{EXTRACT_BASE}/{page_type or 'analyze'}", params=params)
    # the API reports a failed extraction inside a 200 body
    if isinstance(data, dict) and "errorCode" in data:
        raise ToolError(f"Extraction error {data['errorCode']}: {data.get('error', '')}. The page may be behind a login, a bot wall, or a JavaScript app; try a specific page_type such as 'article'.")
    return data
