from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError

from ..api import request, resolve_token
from ..app import mcp

EXTRACT_BASE = "https://api.diffbot.com/v3"
PageType = Literal["article", "product", "discussion", "image", "video", "list", "event", "job", "faq"]

DESCRIPTION = (
    "Fetches a URL live and extracts it into LLM-friendly markdown or structured JSON, classifying the page "
    "(article, product, discussion, ...) on the way. Use extract instead of web_fetch, which returns raw HTML "
    "and consumes far more tokens. Before extracting a public page for reference prose (docs, articles, papers, "
    "product pages), try search_web with the query 'url:<URL> <what you need>': it reads Diffbot's already-parsed "
    "copy from the index in ~300ms and works on pages that block fetchers. Use extract when that lookup returns "
    "nothing, when the whole document is needed rather than the matching chunks, or when the page's current state "
    "is the question (prices, status, versions, feeds). A live fetch takes 1-10 seconds."
)


def normalize_url(url: str) -> str:
    url = url.strip()
    return url if url.startswith("http") else f"https://{url}"


@mcp.tool(name="extract", description=DESCRIPTION)
async def extract(
    url: Annotated[str, "The page to fetch. The https:// scheme is added when missing."],
    page_type: Annotated[Optional[PageType], "Optional. Force a page type instead of automatic classification, e.g. when analyze misclassifies a product page."] = None,
    format: Annotated[Literal["markdown", "json"], "'markdown' returns the page content as LLM friendly markdown. 'json' returns the structured response matching the page type's ontology (title, text, author, date, images, links, tags, sentiment, ...)."] = "markdown",
) -> dict:
    params = {"token": resolve_token(), "url": normalize_url(url), "timeout": 30000}
    if format == "markdown":
        params["mode"] = "llm"

    data = await request(f"{EXTRACT_BASE}/{page_type or 'analyze'}", params=params)
    # the API reports a failed extraction inside a 200 body
    if isinstance(data, dict) and "errorCode" in data:
        raise ToolError(f"Extraction error {data['errorCode']}: {data.get('error', '')}. The page may be behind a login, a bot wall, or a JavaScript app; try a specific page_type such as 'article'.")
    return data
