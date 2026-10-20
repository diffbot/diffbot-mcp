import re
from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import READ_ONLY, mcp
from ..dql import enum_values, find_named, get_ontology, ontology_fields, ontology_names, rank_names, taxonomy_values

DESCRIPTION = (
    "Looks up the Knowledge Graph ontology: entity types, their fields, and taxonomy or enum values. Use before "
    "raw dql to confirm a field path exists and to get the exact spelling of a value (a guessed path is silently "
    "ignored, a guessed value returns zero). Results are ranked best match first."
    " API docs: https://docs.diffbot.com/docs/ontology"
)


@mcp.tool(name="dql_ontology", title="Look Up DQL Ontology", description=DESCRIPTION, annotations=READ_ONLY)
async def dql_ontology(
    action: Annotated[Literal["types", "composites", "enums", "taxonomies", "fields", "taxonomy", "enum", "search"], "fields/taxonomy/enum need name; search needs search"],
    name: Annotated[Optional[str], "Type or composite (fields), or taxonomy/enum name"] = None,
    search: Annotated[Optional[str], "Case-insensitive regex filter"] = None,
    limit: Annotated[int, "Max results; total is always reported"] = 25,
) -> dict:
    ontology = await get_ontology()
    pattern = re.compile(search, re.IGNORECASE) if search else None

    if action in ("fields", "taxonomy", "enum") and not name:
        raise ToolError(f"name is required for action '{action}'")
    if action == "search" and pattern is None:
        raise ToolError("search is required for action 'search'")

    if action in ("types", "composites", "enums", "taxonomies"):
        results = ontology_names(ontology, action)
    elif action == "fields":
        results = ontology_fields(ontology, name, pattern)
    elif action == "taxonomy":
        results = taxonomy_values(ontology, name, pattern)
        if pattern is not None:
            results = rank_names(results, pattern)
    elif action == "enum":
        results = enum_values(ontology, name)
    else:
        results = find_named(ontology, pattern)

    return {
        "action": action,
        "total": len(results),
        "returned": min(len(results), limit),
        "results": results[:limit],
    }
