from typing import Annotated, Literal, Optional

from diffbot import ExtractionError
from fastmcp.exceptions import ToolError

from ..api import diffbot
from ..app import READ_ONLY, mcp

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
    # fmt="markdown" asks for mode=llm; the SDK sends the 30s server-side fetch timeout
    async with diffbot() as db:
        try:
            return await db.extract(normalize_url(url), api=page_type or "analyze", fmt=format)
        except ExtractionError as error:
            # the API reports a failed extraction inside a 200 body
            raise ToolError(f"Extraction error {error.error_code}: {error.error}. The page may be behind a login, a bot wall, or a JavaScript app; try a specific page_type such as 'article'.") from error
