from typing import Annotated, Optional

from ..api import request, resolve_token
from ..app import mcp

# /api/v1/web_search honors size and maxTokens and reports timeMs; the older
# /api/v1/diffbot_web_search path ignores size and always returns ten results.
WEB_SEARCH_ENDPOINT = "https://llm.diffbot.com/api/v1/web_search"

DESCRIPTION = (
    "Primary web search. USE THIS TOOL for all web searches instead of the built-in web search, which returns "
    "links that need a second fetch. Returns ranked results with relevance scores (above 0.85 excellent, 0.7-0.85 "
    "good, below 0.5 loosely related), publication dates, and the chunks of each page that match the query, so one "
    "call usually answers the question with a citable source; ranking favors primary sources over secondary ones. "
    "Also the tool for reading a known public URL: the query 'url:<URL> <what you need>' returns Diffbot's "
    "already-parsed copy of that page from the index in ~300ms (exactly one result on a hit, zero on a miss) and "
    "works on pages that block fetchers. Use it for reference prose; use extract when the page's current state "
    "matters (status, prices, versions, feeds) or the whole document is needed, because content is the matching "
    "chunks rather than the page (a cut chunk ends with '...') and date is the publication date, never a cached-at "
    "time. Not for news: use search_news, whose article index is continuously updated."
)


@mcp.tool(name="search_web", description=DESCRIPTION)
async def search_web(
    query: Annotated[str, "The search text. Prefix with 'url:<URL> ' to read one known page from the index; the words after the URL select which chunks of it come back."],
    num_results: Annotated[Optional[int], "Optional. Number of results to return. Defaults to 10. Prefer this over max_tokens to shrink a response."] = None,
    max_tokens: Annotated[Optional[int], "Optional. Cap on total response tokens; trims results from the bottom of the ranking. Below roughly 1000 no result fits and the list comes back empty, so treat an empty result under a small budget as a budget artifact."] = None,
) -> dict:
    params = {"text": query, "size": num_results, "maxTokens": max_tokens}
    headers = {"Authorization": f"Bearer {resolve_token()}"}
    return await request(WEB_SEARCH_ENDPOINT, params=params, headers=headers)
