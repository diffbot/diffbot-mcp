from typing import Annotated, Optional

from ..api import request, resolve_token
from ..app import READ_ONLY, mcp

# /api/v1/web_search honors size and maxTokens and reports timeMs; the older
# /api/v1/diffbot_web_search path ignores size and always returns ten results.
WEB_SEARCH_ENDPOINT = "https://llm.diffbot.com/api/v1/web_search"

DESCRIPTION = (
    "Web search over Diffbot's index: ranked results with relevance scores, publication dates, and the matching "
    "chunks of each page, so one call usually answers with a citable source. Also a page cache reader: "
    "'url:<URL>' alone returns the full stored page, 'url:<URL> <what you need>' returns only its matching "
    "chunks; both take ~300ms (one result on a hit, zero on a miss) and work on pages that block fetchers. Use "
    "extract when the lookup misses or the page's current state is the question. Not for news (search_news)."
    " API docs: https://docs.diffbot.com/reference/web-search"
)


def is_page_lookup(query: str) -> bool:
    """True for a bare 'url:<URL>' query: the whole stored page is wanted, not the chunks matching extra terms."""
    parts = query.split()
    return len(parts) == 1 and parts[0].lower().startswith("url:")


@mcp.tool(name="search_web", title="Search the Web", description=DESCRIPTION, annotations=READ_ONLY)
async def search_web(
    query: Annotated[str, "Search text; 'url:<URL>' for a full page; 'url:<URL> <terms>' for its chunks"],
    num_results: Annotated[Optional[int], "Results to return (default 10)"] = None,
    max_tokens: Annotated[Optional[int], "Token cap; below ~1000 nothing fits; ignored for a full page"] = None,
) -> dict:
    params = {"text": query.strip(), "size": num_results, "maxTokens": max_tokens}
    if is_page_lookup(query):
        # the full stored markdown instead of reranked chunks; the cross-encoder path always chunks
        params.update(snippetLength="full", rerank="none")
    headers = {"Authorization": f"Bearer {resolve_token()}"}
    return await request(WEB_SEARCH_ENDPOINT, params=params, headers=headers)
