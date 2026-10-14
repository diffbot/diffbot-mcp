from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import PLACE_FIELDS, run
from ..dql_builder import build, clause, compare, name_variants, near_clause, or_clause, sort_clause

DESCRIPTION = (
    "Searches geographic entities in the Diffbot Knowledge Graph: cities, counties, subregions, states, provinces, "
    "countries, and points of interest, by name, population, prominence, containing place, or proximity. USE THIS "
    "when the answer is a list of places or a sourced fact about one such as its population; prefer it over "
    "recalling geographic figures. Rows are places. Set kind to the narrowest type that fits, since type:Place "
    "alone spans 18.5M records including 12M points of interest. Accented names are searched in both spellings. "
    "There is no continent field; continent is text-matched and over-inclusive. The KG holds duplicate records for "
    "the same place (city proper vs metro), so collapse same-name rows in the same parent and say which figure was "
    "kept. Returns the DQL it ran."
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


@mcp.tool(name="search_places", description=DESCRIPTION)
async def search_places(
    kind: Annotated[Kind, "'country' (634), 'region' for states and provinces, 'subregion' for counties, 'city', 'administrative_area' for all four, 'poi' for parks, landmarks and venues, 'any'."] = "any",
    name: Annotated[Optional[str], "Place name, matched exactly in accented and plain spelling. Add country or region to pin one of many."] = None,
    descriptors: Annotated[Optional[str], "Free-text descriptor, e.g. 'national park'; mostly for kind 'poi'."] = None,
    country: Annotated[Optional[str], "Containing country, full name."] = None,
    region: Annotated[Optional[str], "Containing state, province, or region."] = None,
    subregion: Annotated[Optional[str], "Containing county or district."] = None,
    within: Annotated[Optional[str], "Any containing place at any level; use country/region/subregion when the level matters."] = None,
    continent: Annotated[Optional[str], "Continent name; text-matched because no continent field exists, so over-inclusive."] = None,
    near: Annotated[Optional[str], "Place to search around, e.g. 'Paris'."] = None,
    radius: Annotated[Optional[str], "Radius for near, e.g. '50km' or '20mi'. Defaults to 15km."] = None,
    min_population: Annotated[Optional[int], "Minimum population."] = None,
    max_population: Annotated[Optional[int], "Maximum population."] = None,
    sort: Annotated[Optional[Sort], "Leave unset unless the ordering is the question ('largest cities')."] = None,
    facet: Annotated[Optional[Literal["placeType"]], "'placeType' shows what mix of cities, subregions, and points of interest a name spans."] = None,
    size: Annotated[int, "Maximum number of places to return."] = 10,
    offset: Annotated[int, "Number of places to skip, for paging."] = 0,
) -> dict:
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
