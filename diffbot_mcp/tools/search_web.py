from typing import Annotated, Optional

from ..api import request, resolve_token
from ..app import mcp

# /api/v1/web_search honors size and maxTokens and reports timeMs; the older
# /api/v1/diffbot_web_search path ignores size and always returns ten results.
WEB_SEARCH_ENDPOINT = "https://llm.diffbot.com/api/v1/web_search"

DESCRIPTION = (
    "Web search over Diffbot's index: ranked results with relevance scores, publication dates, and the matching "
    "chunks of each page, so one call usually answers with a citable source. Also reads a known URL: query "
    "'url:<URL> <what you need>' returns the indexed copy in ~300ms (one result on a hit, zero on a miss) and works "
    "on pages that block fetchers; use extract when the page's current state or the whole document is needed. "
    "Not for news (search_news)."
)


@mcp.tool(name="search_web", description=DESCRIPTION)
async def search_web(
    query: Annotated[str, "Search text, or 'url:<URL> <what you need>'"],
    num_results: Annotated[Optional[int], "Results to return (default 10)"] = None,
    max_tokens: Annotated[Optional[int], "Token cap; below ~1000 nothing fits"] = None,
) -> dict:
    params = {"text": query, "size": num_results, "maxTokens": max_tokens}
    headers = {"Authorization": f"Bearer {resolve_token()}"}
    return await request(WEB_SEARCH_ENDPOINT, params=params, headers=headers)
