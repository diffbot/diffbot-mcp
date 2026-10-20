from typing import Annotated, Literal, Optional

from ..app import READ_ONLY, mcp
from ..dql import run

DESCRIPTION = (
    "Runs a DQL query against the Diffbot Knowledge Graph for any entity type or shape the typed tools "
    "(search_organizations, search_people, search_news, search_deals, search_places) do not cover: products, "
    "patents, job posts, facets, cross-entity queries, or an id filter from resolve_entities. Each typed tool "
    "returns the DQL it ran, which can be refined here. Rules: conditions on one nested list object go inside one "
    "{} (employments.{employer.name:X isCurrent:true}); confirm field paths and taxonomy spellings with dql_ontology "
    "since an unknown path is silently ignored; probe variants with dql_probe before pulling rows; do not add a sort "
    "unless ordering is the question (articles excepted: sortBy:date). For a CSV file, do not page rows: GET https://kg.diffbot.com/kg/v3/dql?token=..&format=csv&size=<hits>&exportspec=<fields>&query=<DQL> straight to disk."
    " API docs: https://docs.diffbot.com/docs/dql-quickstart"
)


@mcp.tool(name="dql", title="Run DQL Query", description=DESCRIPTION, annotations=READ_ONLY)
async def dql(
    query: Annotated[str, "DQL, starting with type:X"],
    size: Annotated[int, "Max rows or buckets"] = 10,
    offset: Annotated[int, "Rows to skip"] = 0,
    fields: Annotated[Optional[str], "csv columns as 'path,Label;path,Label'"] = None,
    format: Annotated[Literal["csv", "json"], "'json' for full records; add get:a,b to limit"] = "csv",
    hits_only: Annotated[bool, "Count only"] = False,
) -> dict:
    return await run(query, size=size, offset=offset, fields=fields, format=format, hits_only=hits_only)
