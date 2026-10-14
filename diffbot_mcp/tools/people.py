from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import DEFAULT_FIELDS, resolve_value, run
from ..dql_builder import build, clause, compare, expand_titles, looks_like_domain, or_clause, sort_clause, subquery

DESCRIPTION = (
    "Searches people in the Diffbot Knowledge Graph by job title, employer, employer industry, skills, education, "
    "location, or nationality. USE THIS when the answer is a list of people: executives at a company, alumni of a "
    "school, who holds a role, who has a skill, who runs a company. Rows are people, not companies. Every "
    "employment condition is co-constrained on one job, C-suite titles are expanded to both their spelled-out and "
    "abbreviated forms, and the Title and Employer columns show the job that matched rather than the person's "
    "primary one. For the CEO or founders of one named company use leadership_of, which reads the curated fields "
    "on the Organization instead of scanning people. Coverage is people with a public online professional presence "
    "only: an empty result means not publicly documented, never that a person or role does not exist, and counts "
    "are a floor, not a headcount. Not a people-finder for private individuals. Returns the DQL it ran."
)

Sort = Literal["importance", "net_worth"]
SORT_FIELDS = {"importance": "importance", "net_worth": "netWorth.value"}
LEADERSHIP_GET = "get:name,ceo,founders"
MATCHED_GET = "get:id,name,employments,location,linkedInUri"


def build_people_query(
    *,
    name: Optional[str] = None,
    title: Optional[List[str]] = None,
    employer: Optional[str] = None,
    employer_industry: Optional[str] = None,
    employer_country: Optional[str] = None,
    employer_min_employees: Optional[int] = None,
    current: bool = True,
    school: Optional[str] = None,
    major: Optional[str] = None,
    degree: Optional[str] = None,
    skill: Optional[List[str]] = None,
    city: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    nationality: Optional[str] = None,
    gender: Optional[str] = None,
    min_net_worth: Optional[float] = None,
    sort: Optional[Sort] = None,
) -> str:
    """employer_industry and gender must already be exact taxonomy/enum values."""
    clauses = ["type:Person"]
    if name:
        clauses.append(clause("name", name, strict=True))

    # every condition about one job goes inside one {}; written separately they match
    # different jobs and inflate the count roughly nine times
    employment = []
    if title:
        employment.append(or_clause("title", expand_titles(title)))
    if employer:
        employment.append(clause("employer.name", employer))
    if employer_industry:
        employment.append(clause("employer.categories.name", employer_industry))
    if employer_country:
        employment.append(clause("employer.location.country.name", employer_country))
    if employer_min_employees is not None:
        employment.append(compare("employer.nbEmployees", ">=", employer_min_employees))
    if employment and current:
        employment.append("isCurrent:true")
    clauses.append(subquery("employments", employment))

    education = []
    if school:
        education.append(clause("institution.name", school))
    if major:
        education.append(clause("major.name", major))
    if degree:
        education.append(clause("degree.name", degree))
    clauses.append(subquery("educations", education))

    if skill:
        clauses.append(or_clause("skills.name", skill))
    for level, value in (("city", city), ("region", region), ("country", country)):
        if value:
            clauses.append(clause(f"location.{level}.name", value))
    if nationality:
        clauses.append(clause("nationalities.name", nationality))
    if gender:
        clauses.append(clause("gender", gender))
    if min_net_worth is not None:
        clauses.append(compare("netWorth.value", ">=", min_net_worth))

    if len([c for c in clauses if c]) == 1:
        raise ToolError("search_people needs at least one filter.")
    if sort:
        clauses.append(sort_clause(SORT_FIELDS[sort], descending=True))
    return build(clauses)


def build_leadership_query(company: str) -> str:
    # the domain plus the default ranking is right for apple.com, tesla.com, openai.com and
    # friends, where strict:name misses (Apple Inc.) and a sort surfaces the wrong record
    anchor = clause("homepageUri", company) if looks_like_domain(company) else clause("name", company)
    return build(["type:Organization", anchor, LEADERSHIP_GET])


def pick_employment(employments: List[dict], employer: Optional[str], titles: List[str], current: bool) -> dict:
    """The employment that best matches the filters, so rendered columns reflect the matched job rather than the primary one."""
    def score(job: dict) -> int:
        points = 0
        employer_name = ((job.get("employer") or {}).get("name") or "").lower()
        if employer and employer.lower() in employer_name:
            points += 4
        job_title = (job.get("title") or "").lower()
        if titles and any(t.lower() in job_title for t in titles):
            points += 2
        if current and job.get("isCurrent"):
            points += 1
        return points

    return max(employments, key=score) if employments else {}


def render_person(entity: dict, employer: Optional[str], titles: List[str], current: bool) -> dict:
    job = pick_employment(entity.get("employments") or [], employer, titles, current)
    location = entity.get("location") or {}
    row = {
        "Name": entity.get("name"),
        "Title": job.get("title"),
        "Employer": (job.get("employer") or {}).get("name"),
        "City": (location.get("city") or {}).get("name"),
        "Country": (location.get("country") or {}).get("name"),
        "LinkedIn": entity.get("linkedInUri"),
        "Id": entity.get("id"),
    }
    return {key: value for key, value in row.items() if value}


@mcp.tool(name="search_people", description=DESCRIPTION)
async def search_people(
    name: Annotated[Optional[str], "Person's name, matched exactly. Expect several rows for one individual."] = None,
    title: Annotated[Optional[List[str]], "Job titles, OR-ed. CEO, CTO, CFO, COO, CIO, CMO and 'board member' are expanded to every spelling."] = None,
    employer: Annotated[Optional[str], "Employer name, e.g. 'Nvidia'."] = None,
    employer_industry: Annotated[Optional[str], "OrganizationCategory of the employer, e.g. 'Biotechnology Companies'. Free text is resolved; ambiguous text returns candidates."] = None,
    employer_country: Annotated[Optional[str], "Country of the employer's headquarters, full name."] = None,
    employer_min_employees: Annotated[Optional[int], "Minimum headcount of the employer."] = None,
    current: Annotated[bool, "Only current employment; set false for history (everyone who has worked at X)."] = True,
    school: Annotated[Optional[str], "Educational institution, e.g. 'Stanford University'."] = None,
    major: Annotated[Optional[str], "Field of study, e.g. 'Computer Science'."] = None,
    degree: Annotated[Optional[str], "Degree name, e.g. 'MBA'."] = None,
    skill: Annotated[Optional[List[str]], "Skills, OR-ed, e.g. ['Machine Learning']."] = None,
    city: Annotated[Optional[str], "City of primary residence."] = None,
    region: Annotated[Optional[str], "State, province, or region of primary residence."] = None,
    country: Annotated[Optional[str], "Country of primary residence, full name."] = None,
    nationality: Annotated[Optional[str], "Nationality as a country name, e.g. 'France'."] = None,
    gender: Annotated[Optional[str], "Gender enum value, e.g. 'Female'."] = None,
    min_net_worth: Annotated[Optional[float], "Minimum net worth; the top of the range holds bad outliers, so sanity-check rows."] = None,
    sort: Annotated[Optional[Sort], "Leave unset unless the ordering is the question; the default ranking already orders by importance."] = None,
    leadership_of: Annotated[Optional[str], "A company's homepage domain (preferred) or name; returns its CEO and founders from the curated Organization fields. Other filters are ignored."] = None,
    size: Annotated[int, "Maximum number of people to return."] = 10,
    offset: Annotated[int, "Number of people to skip, for paging."] = 0,
) -> dict:
    if leadership_of:
        result = await run(build_leadership_query(leadership_of), size=1, format="json")
        records = result.get("results") or []
        if not records:
            return {"dql": result["dql"], "hits": result.get("hits"), "company": None, "ceo": None, "founders": [], "notes": ["No organization matched. Prefer the homepage domain over the name."]}
        entity = records[0]
        return {
            "dql": result["dql"],
            "hits": result.get("hits"),
            "company": entity.get("name"),
            "ceo": (entity.get("ceo") or {}).get("name"),
            "founders": [f.get("name") for f in entity.get("founders") or [] if f.get("name")],
        }

    notes: List[str] = []
    if employer_industry:
        resolved = await resolve_value("OrganizationCategory", employer_industry)
        if resolved.value is None:
            if resolved.candidates:
                return {"dql": None, "candidates": {"employer_industry": resolved.candidates}, "notes": [resolved.note]}
            raise ToolError(resolved.note)
        employer_industry = resolved.value
        if resolved.note:
            notes.append(resolved.note)
    if gender:
        resolved = await resolve_value("Gender", gender, kind="enum")
        if resolved.value is None:
            raise ToolError(resolved.note)
        gender = resolved.value

    query = build_people_query(
        name=name, title=title, employer=employer, employer_industry=employer_industry, employer_country=employer_country,
        employer_min_employees=employer_min_employees, current=current, school=school, major=major, degree=degree,
        skill=skill, city=city, region=region, country=country, nationality=nationality, gender=gender,
        min_net_worth=min_net_worth, sort=sort,
    )

    # with an employer or title filter the rendered job must be the one that matched, not
    # the primary one, so the records are read as json and the matching employment picked
    if employer or title:
        result = await run(f"{query} {MATCHED_GET}", size=size, offset=offset, format="json", bare_type_check=True)
        titles = expand_titles(title or [])
        result["results"] = [render_person(entity, employer, titles, current) for entity in result.get("results") or []]
        result["dql"] = query
    else:
        result = await run(query, size=size, offset=offset, fields=DEFAULT_FIELDS["Person"], bare_type_check=True)

    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
