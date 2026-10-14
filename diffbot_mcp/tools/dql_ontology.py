import re
from typing import Annotated, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import enum_values, find_named, get_ontology, ontology_fields, ontology_names, rank_names, taxonomy_values

DESCRIPTION = (
    "Looks up the entity types, fields, taxonomies, and enums that make up the Diffbot Knowledge Graph. Use before "
    "writing a dql query to confirm that a field path exists and to find the exact spelling of a taxonomy or enum "
    "value, since a guessed field name is silently ignored and a guessed value returns zero. 'types', "
    "'composites', 'enums' and 'taxonomies' list the available names; 'fields' lists the fields of one entity type "
    "or composite (Organization, Location, Employment); 'taxonomy' and 'enum' list the values one may hold "
    "(OrganizationCategory, ArticleCategory, Language, Gender); 'search' finds a name anywhere in the ontology when "
    "its location is unknown. Deprecated fields are omitted. A query may descend from a composite or linked field "
    "into its own fields, as in location.city.name or employments.employer.categories.name."
)


@mcp.tool(name="dql_ontology", description=DESCRIPTION)
async def dql_ontology(
    action: Annotated[Literal["types", "composites", "enums", "taxonomies", "fields", "taxonomy", "enum", "search"], "The lookup to perform. 'fields', 'taxonomy' and 'enum' require name. 'search' requires search."],
    name: Annotated[Optional[str], "The entity type or composite to list fields of (e.g. 'Organization', 'Location'), or the taxonomy or enum to list values of. Required for 'fields', 'taxonomy' and 'enum'."] = None,
    search: Annotated[Optional[str], "A regular expression, matched case insensitively, to filter results by name. Required for 'search' and optional for 'fields' and 'taxonomy'."] = None,
    limit: Annotated[int, "Maximum number of results to return; best matches first. The total is always reported so a truncated lookup can be narrowed with search."] = 25,
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
