from typing import Annotated, List

from ..app import mcp
from ..dql import probe

DESCRIPTION = (
    "Hit counts for several DQL queries at once, to compare variants before pulling rows (co-constrained {} vs "
    "loose, category vs descriptors). Zero hits means a wrong value (check dql_ontology); a count equal to the bare "
    "type:X count means a field path was ignored. similarTo cannot be probed; never probe an unfiltered type:Article."
)


@mcp.tool(name="dql_probe", description=DESCRIPTION)
async def dql_probe(
    queries: Annotated[List[str], "DQL queries, each starting with type:X"],
) -> dict:
    return {"results": await probe(queries)}
