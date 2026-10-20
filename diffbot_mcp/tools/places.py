from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import READ_ONLY, mcp
from ..dql import PLACE_FIELDS, run
from ..dql_builder import build, clause, compare, name_variants, near_clause, or_clause, sort_clause, parse_range, split_near

DESCRIPTION = (
    "Cities, counties, states, provinces, countries, and points of interest in the Diffbot Knowledge Graph by "
    "name, population, containing place, or proximity. Use when the answer is a list of places or a sourced fact "
    "about one such as population. Set kind to the narrowest type that fits. Returns rows plus the DQL it ran."
    " API docs: https://docs.diffbot.com/docs/dql-quickstart"
)

Kind = Literal["city", "subregion", "region", "country", "administrative_area", "poi", "any"]
KIND_CLAUSES = {
    "city": "type:City",
    "subregion": "type:Subregion",
    "region": "type:Region",
    "country": "type:Country",
    "administrative_area": "type:AdministrativeArea",
    "poi": 'type:Place not(types:"AdministrativeArea")',
    "any": "type:Place",
}
Sort = Literal["population", "importance"]


def build_places_query(
    *,
    kind: Kind = "any",
    name: Optional[str] = None,
    descriptors: Optional[str] = None,
    country: Optional[str] = None,
    region: Optional[str] = None,
    subregion: Optional[str] = None,
    within: Optional[str] = None,
    continent: Optional[str] = None,
    near: Optional[str] = None,
    radius: Optional[str] = None,
    min_population: Optional[int] = None,
    max_population: Optional[int] = None,
    sort: Optional[Sort] = None,
    facet: Optional[Literal["placeType"]] = None,
) -> tuple:
    """Return (dql, notes)."""
    clauses = [KIND_CLAUSES[kind]]
    notes: List[str] = []

    if name:
        # diacritics are not normalized and coverage of each spelling is inconsistent
        clauses.append(or_clause("name", name_variants(name), strict=True))
    if descriptors:
        clauses.append(clause("descriptors", descriptors))
    for level, value in (("country", country), ("region", region), ("subregion", subregion)):
        if value:
            clauses.append(clause(f"location.{level}.name", value))
    if within:
        clauses.append(clause("isPartOf.name", within))
    if continent:
        clauses.append(clause("description", f"in {continent}"))
        notes.append(f"There is no continent field; '{continent}' was matched against the prose description, which is over-inclusive and double-counts duplicate records. Filter the list before presenting it and say it was text-matched.")
    if near:
        clauses.append(near_clause(near, radius))
    if min_population is not None:
        clauses.append(compare("population", ">=", min_population))
    if max_population is not None:
        clauses.append(compare("population", "<=", max_population))

    if len(clauses) == 1 and kind in ("any", "administrative_area", "poi"):
        raise ToolError("search_places needs a name, containing place, or other filter for this kind.")

    if facet:
        clauses.append(f"facet:{facet}")
    elif sort:
        clauses.append(sort_clause(sort, descending=True))
    return build(clauses), notes


@mcp.tool(name="search_places", title="Search Places", description=DESCRIPTION, annotations=READ_ONLY)
async def search_places(
    kind: Annotated[Kind, "country | region | subregion | city | administrative_area | poi | any"] = "any",
    name: Annotated[Optional[str], "Place name, exact"] = None,
    descriptors: Annotated[Optional[str], "Free text, e.g. 'national park' (poi)"] = None,
    country: Annotated[Optional[str], "Containing country"] = None,
    region: Annotated[Optional[str], "Containing state/region"] = None,
    subregion: Annotated[Optional[str], "Containing county/district"] = None,
    within: Annotated[Optional[str], "Containing place, any level"] = None,
    continent: Annotated[Optional[str], "Continent (text match, loose)"] = None,
    near: Annotated[Optional[str], "Place and radius, e.g. 'Paris 50km'"] = None,
    population: Annotated[Optional[str], "Range, e.g. '1M+', '10000-50000'"] = None,
    sort: Annotated[Optional[Sort], "Only if ordering is the question"] = None,
    facet: Annotated[Optional[Literal["placeType"]], "Bucket by place type"] = None,
    size: Annotated[int, "Max rows"] = 10,
    offset: Annotated[int, "Rows to skip"] = 0,
) -> dict:
    near, radius = split_near(near)
    min_population, max_population = parse_range(population, "population", integer=True)
    query, notes = build_places_query(
        kind=kind, name=name, descriptors=descriptors, country=country, region=region, subregion=subregion,
        within=within, continent=continent, near=near, radius=radius, min_population=min_population,
        max_population=max_population, sort=sort, facet=facet,
    )
    result = await run(query, size=size, offset=offset, fields=PLACE_FIELDS, bare_type_check=True)
    if result.get("hits") == 0 and name:
        notes.append("Zero hits for both spellings of the name. Try kind 'any', or match on country/region without the name.")
    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
