from typing import Annotated, List

from ..app import mcp
from ..dql import probe

DESCRIPTION = (
    "Returns the hit count of several DQL queries at once, run in parallel, so candidate variants can be compared "
    "before pulling rows: the {} co-constrained form against the loose form, a category filter against a "
    "descriptors filter, with and without a location. Aim for a few hundred to a few thousand hits. Two failure "
    "signatures: zero hits means a value is wrong for the field (check dql_ontology), and a count equal to the "
    "bare type:X count means a field path was silently ignored. similarTo queries cannot be probed and are "
    "reported as errors. Never probe an unfiltered type:Article; the article index is large enough that it times out."
)


@mcp.tool(name="dql_probe", description=DESCRIPTION)
async def dql_probe(
    queries: Annotated[List[str], "The DQL queries to count. Each must begin with a type: clause."],
) -> dict:
    return {"results": await probe(queries)}
