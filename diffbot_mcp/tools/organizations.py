from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import DEFAULT_FIELDS, resolve_value, run
from ..dql_builder import build, clause, compare, looks_like_domain, near_clause, or_clause, sort_clause, validate_date, subquery

DESCRIPTION = (
    "Searches companies and organizations in the Diffbot Knowledge Graph by industry, headquarters, headcount, "
    "revenue, funding, ownership, or leadership, plus similar_to lookalike lists for competitor mapping. USE THIS "
    "when the answer is a list of companies: prospecting, market maps, competitor sets, who-does-X, everything a "
    "company acquired, everything an investor backed. Rows are companies, not deals. industry is the best first "
    "filter and is resolved against the OrganizationCategory taxonomy; descriptors is the free-text fallback for a "
    "niche. Location is the headquarters unless any_office is set. A specific company is matched by name exactly "
    "or better by homepage domain. Set facet for distribution questions. Returns the DQL it ran; refine with dql "
    "when the shape is outside these parameters."
)

Sort = Literal["employees", "revenue", "founded", "importance"]
SORT_FIELDS = {"employees": "nbEmployees", "revenue": "revenue.value", "founded": "foundingDate", "importance": "importance"}


def build_organizations_query(
    *,
    name: Optional[str] = None,
    name_match: Literal["strict", "contains"] = "strict",
    homepage: Optional[str] = None,
    industry: Optional[List[str]] = None,
    primary_industry: bool = True,
    descriptors: Optional[str] = None,
    city: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    any_office: bool = False,
    near: Optional[str] = None,
    radius: Optional[str] = None,
    min_employees: Optional[int] = None,
    max_employees: Optional[int] = None,
    min_revenue: Optional[float] = None,
    max_revenue: Optional[float] = None,
    is_public: Optional[bool] = None,
    founded_after: Optional[str] = None,
    founded_before: Optional[str] = None,
    investor: Optional[str] = None,
    acquired_by: Optional[str] = None,
    similar_to: Optional[str] = None,
    sort: Optional[Sort] = None,
    facet: Optional[str] = None,
) -> str:
    """industry values must already be exact OrganizationCategory names."""
    clauses = ["type:Organization"]

    if similar_to:
        anchor = clause("homepageUri", similar_to) if looks_like_domain(similar_to) else clause("name", similar_to)
        clauses.append(f"similarTo({anchor})")
    if name:
        clauses.append(clause("name", name, strict=name_match == "strict"))
    if homepage:
        clauses.append(clause("homepageUri", homepage))
    if industry:
        if primary_industry:
            # categories.{...} co-constrains name and isPrimary on the same category entry;
            # the loose categories.name form also matches secondary tags (hospitals tagged software).
            clauses.append(subquery("categories", [or_clause("name", industry), "isPrimary:true"]))
        else:
            clauses.append(or_clause("categories.name", industry))
    if descriptors:
        clauses.append(clause("descriptors", descriptors))

    # singular location is the headquarters; plural locations is any office
    prefix = "locations" if any_office else "location"
    for level, value in (("city", city), ("region", region), ("country", country)):
        if value:
            clauses.append(clause(f"{prefix}.{level}.name", value))
    if near:
        clauses.append(near_clause(near, radius))

    if min_employees is not None:
        clauses.append(compare("nbEmployees", ">=", min_employees))
    if max_employees is not None:
        clauses.append(compare("nbEmployees", "<=", max_employees))
    if min_revenue is not None:
        clauses.append(compare("revenue.value", ">=", min_revenue))
    if max_revenue is not None:
        clauses.append(compare("revenue.value", "<=", max_revenue))
    if is_public is not None:
        clauses.append(f"isPublic:{'true' if is_public else 'false'}")
    if founded_after:
        clauses.append(compare("foundingDate", ">=", validate_date(founded_after, "founded_after")))
    if founded_before:
        clauses.append(compare("foundingDate", "<=", validate_date(founded_before, "founded_before")))
    if investor:
        clauses.append(clause("investments.investors.name", investor))
    if acquired_by:
        clauses.append("isAcquired:true")
        clauses.append(clause("acquiredBy.name", acquired_by))

    if len(clauses) == 1:
        raise ToolError("search_organizations needs at least one filter.")

    if facet:
        clauses.append(f"facet:{facet}")
    elif sort:
        clauses.append(sort_clause(SORT_FIELDS[sort], descending=True))
    return build(clauses)


@mcp.tool(name="search_organizations", description=DESCRIPTION)
async def search_organizations(
    name: Annotated[Optional[str], "Company name, matched exactly by default (contains-matching over-matches badly). Large companies have duplicate records; the top row is the primary one."] = None,
    name_match: Annotated[Literal["strict", "contains"], "'contains' only when strict returns nothing or the name is a kind of company rather than a specific one."] = "strict",
    homepage: Annotated[Optional[str], "Homepage domain, e.g. 'tesla.com'; the most reliable way to pin one company."] = None,
    industry: Annotated[Optional[List[str]], "OrganizationCategory values, OR-ed, e.g. ['Semiconductor Companies']. Free text is resolved; ambiguous text returns candidates."] = None,
    primary_industry: Annotated[bool, "Match industry against each company's primary category only (default). Set False to also match secondary tags, which widens recall but admits mis-tagged rows such as hospitals or sports leagues tagged as software."] = True,
    descriptors: Annotated[Optional[str], "Free-text capability tag, e.g. 'GPU'; the fallback when no industry fits."] = None,
    city: Annotated[Optional[str], "Headquarters city."] = None,
    region: Annotated[Optional[str], "Headquarters state, province, or region."] = None,
    country: Annotated[Optional[str], "Headquarters country, full name, e.g. 'United States'."] = None,
    any_office: Annotated[bool, "Match any office in the given location rather than the headquarters."] = False,
    near: Annotated[Optional[str], "Place to search around, e.g. 'Austin'; use for 'near' or 'within X miles'."] = None,
    radius: Annotated[Optional[str], "Radius for near, e.g. '30mi' or '50km'. Defaults to 15km."] = None,
    min_employees: Annotated[Optional[int], "Minimum headcount."] = None,
    max_employees: Annotated[Optional[int], "Maximum headcount."] = None,
    min_revenue: Annotated[Optional[float], "Minimum annual revenue, as a plain number in the company's reporting currency, e.g. 10000000 for $10M."] = None,
    max_revenue: Annotated[Optional[float], "Maximum annual revenue, same units as min_revenue."] = None,
    is_public: Annotated[Optional[bool], "Publicly traded or not."] = None,
    founded_after: Annotated[Optional[str], "Earliest founding date, YYYY-MM-DD."] = None,
    founded_before: Annotated[Optional[str], "Latest founding date, YYYY-MM-DD."] = None,
    investor: Annotated[Optional[str], "Investor name; returns its portfolio companies."] = None,
    acquired_by: Annotated[Optional[str], "Acquirer name; returns the companies it acquired."] = None,
    similar_to: Annotated[Optional[str], "Anchor company (name or homepage domain) for a lookalike list of exactly size companies; other filters narrow within the ranking."] = None,
    sort: Annotated[Optional[Sort], "Leave unset unless the ordering is the question; the default ranking is better."] = None,
    facet: Annotated[Optional[str], "Aggregate into buckets instead of rows, e.g. 'categories.name'; size becomes the bucket count."] = None,
    size: Annotated[int, "Maximum number of companies (or buckets) to return."] = 10,
    offset: Annotated[int, "Number of companies to skip, for paging."] = 0,
) -> dict:
    notes: List[str] = []
    resolved_industry: List[str] = []
    for value in industry or []:
        resolved = await resolve_value("OrganizationCategory", value)
        if resolved.value is None:
            if resolved.candidates:
                return {"dql": None, "candidates": {"industry": resolved.candidates}, "notes": [resolved.note]}
            notes.append(f"{resolved.note}; matched descriptors on '{value}' instead.")
            descriptors = descriptors or value
        else:
            resolved_industry.append(resolved.value)
            if resolved.note:
                notes.append(resolved.note)

    query = build_organizations_query(
        name=name, name_match=name_match, homepage=homepage, industry=resolved_industry, primary_industry=primary_industry, descriptors=descriptors,
        city=city, region=region, country=country, any_office=any_office, near=near, radius=radius,
        min_employees=min_employees, max_employees=max_employees, min_revenue=min_revenue, max_revenue=max_revenue,
        is_public=is_public,
        founded_after=founded_after, founded_before=founded_before, investor=investor, acquired_by=acquired_by,
        similar_to=similar_to, sort=sort, facet=facet,
    )
    result = await run(query, size=size, offset=offset, fields=DEFAULT_FIELDS["Organization"], bare_type_check=True)
    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
