import pathlib
from typing import Annotated, Optional

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request

from ..app import mcp
from ..dql import export

DESCRIPTION = (
    "Exports DQL results as a CSV file: the whole result set, not a page. Takes the dql string any search tool "
    "returns. With path, writes the file where the server runs and returns its location; without path, returns "
    "the CSV text (keep size small then). Columns default per entity type."
)


def _on_http() -> bool:
    try:
        get_http_request()
    except RuntimeError:
        return False
    return True


@mcp.tool(name="export_csv", description=DESCRIPTION)
async def export_csv(
    query: Annotated[str, "DQL, starting with type:X"],
    path: Annotated[Optional[str], "File to write, e.g. ~/exports/ma-software.csv"] = None,
    fields: Annotated[Optional[str], "Columns as 'path,Label;path,Label'"] = None,
    size: Annotated[int, "Max rows"] = 1000,
    offset: Annotated[int, "Rows to skip"] = 0,
) -> dict:
    if path and _on_http():
        raise ToolError("The hosted server cannot write files. Call export_csv without path to receive the CSV text, or run the server locally over stdio.")
    result = await export(query, size=size, offset=offset, fields=fields)
    if not path:
        return result
    target = pathlib.Path(path).expanduser()
    if target.exists() and target.is_dir():
        raise ToolError(f"{target} is a directory; give a file path ending in .csv")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = result.pop("csv")
    target.write_text(text, encoding="utf-8")
    result["path"] = str(target)
    result["bytes"] = len(text.encode("utf-8"))
    return result
