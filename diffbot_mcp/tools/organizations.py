from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import DEFAULT_FIELDS, resolve_value, run
from ..dql_builder import build, clause, compare, looks_like_domain, near_clause, or_clause, sort_clause, validate_date, subquery, parse_date_range, parse_range, split_near

DESCRIPTION = (
    "Companies in the Diffbot Knowledge Graph by industry, location, headcount, revenue, founding date, investor, "
    "acquirer, or lookalikes of a named company. Use when the answer is a list of companies or one company's record "
    "(not deals or people). Returns rows plus the DQL it ran."
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
    name: Annotated[Optional[str], "Company name or homepage domain"] = None,
    industry: Annotated[Optional[List[str]], "Industries (OR); free text ok"] = None,
    primary_industry: Annotated[bool, "False: also match secondary tags"] = True,
    city: Annotated[Optional[str], "HQ city"] = None,
    region: Annotated[Optional[str], "HQ state/region"] = None,
    country: Annotated[Optional[str], "HQ country"] = None,
    near: Annotated[Optional[str], "Place and radius, e.g. 'Austin 30mi'"] = None,
    revenue: Annotated[Optional[str], "Range, e.g. '10M-75M', '1B+'"] = None,
    employees: Annotated[Optional[str], "Range, e.g. '50-500', '<20'"] = None,
    founded: Annotated[Optional[str], "Year or range, e.g. '2015-2020'"] = None,
    is_public: Annotated[Optional[bool], "Publicly traded"] = None,
    investor: Annotated[Optional[str], "Investor: its portfolio"] = None,
    acquired_by: Annotated[Optional[str], "Acquirer: its acquisitions"] = None,
    similar_to: Annotated[Optional[str], "Anchor company for lookalikes"] = None,
    sort: Annotated[Optional[Sort], "Only if ordering is the question"] = None,
    facet: Annotated[Optional[str], "Bucket by field, e.g. categories.name"] = None,
    size: Annotated[int, "Max rows"] = 10,
    offset: Annotated[int, "Rows to skip"] = 0,
) -> dict:
    min_revenue, max_revenue = parse_range(revenue, "revenue")
    min_employees, max_employees = parse_range(employees, "employees")
    min_employees = int(min_employees) if min_employees is not None else None
    max_employees = int(max_employees) if max_employees is not None else None
    founded_after, founded_before = parse_date_range(founded, "founded")
    near, radius = split_near(near)
    any_office = False  # headquarters only; the prompt shows the raw locations.* form for any-office matching
    homepage = name if name and looks_like_domain(name) else None
    name = None if homepage else name
    descriptors: Optional[str] = None

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
        name=name, name_match="strict", homepage=homepage, industry=resolved_industry, primary_industry=primary_industry, descriptors=descriptors,
        city=city, region=region, country=country, any_office=any_office, near=near, radius=radius,
        min_employees=min_employees, max_employees=max_employees, min_revenue=min_revenue, max_revenue=max_revenue,
        is_public=is_public,
        founded_after=founded_after, founded_before=founded_before, investor=investor, acquired_by=acquired_by,
        similar_to=similar_to, sort=sort, facet=facet,
    )
    result = await run(query, size=size, offset=offset, fields=DEFAULT_FIELDS["Organization"], bare_type_check=True)
    if name and not similar_to and not facet and result.get("hits") == 0:
        # exact name missed: retry with contains-matching, which over-matches but beats an empty answer
        query = build_organizations_query(
            name=name, name_match="contains", industry=resolved_industry, descriptors=descriptors,
            city=city, region=region, country=country, any_office=any_office, near=near, radius=radius,
            min_employees=min_employees, max_employees=max_employees, min_revenue=min_revenue, max_revenue=max_revenue,
            is_public=is_public, founded_after=founded_after, founded_before=founded_before, investor=investor,
            acquired_by=acquired_by, primary_industry=primary_industry, sort=sort,
        )
        result = await run(query, size=size, offset=offset, fields=DEFAULT_FIELDS["Organization"], bare_type_check=True)
        notes.append(f"No exact match for '{name}'; showing contains-matches, which may include unrelated companies.")
    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
