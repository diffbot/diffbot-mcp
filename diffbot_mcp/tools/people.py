from typing import Annotated, List, Literal, Optional, Union

from fastmcp.exceptions import ToolError

from ..app import READ_ONLY, mcp
from ..dql import DEFAULT_FIELDS, resolve_value, run
from ..dql_builder import build, clause, compare, expand_titles, looks_like_domain, or_clause, parse_range, sort_clause, subquery

DESCRIPTION = (
    "People structured search over the Diffbot Knowledge Graph. Prefer for leadership teams, executive and role "
    "lookups, alumni lists, skill-based sourcing, and profile facts on a named person. Filter by job title, "
    "employer, employer industry or size, school, major, skills, residence, nationality, or net worth. Prefer over "
    "a generic web search when the answer involves structured people data. Covers people with a public "
    "professional presence only. For companies use search_organizations."
    " API docs: https://www.diffbot.com/docs/dql/"
)

Sort = Literal["importance", "net_worth"]
SORT_FIELDS = {"importance": "importance", "net_worth": "netWorth.value"}
LEADERSHIP_GET = "get:name,ceo,founders"
MATCHED_GET = "get:id,name,employments,location,linkedInUri"


def place_clause(prefix: str, place: Optional[str]) -> str:
    """A place that may be a city or a country: or(prefix.city.name:X, prefix.country.name:X)."""
    if not place:
        return ""
    return f'or({clause(f"{prefix}.city.name", place)}, {clause(f"{prefix}.country.name", place)})'


def build_people_query(
    *,
    name: Optional[Union[str, List[str]]] = None,
    title: Optional[List[str]] = None,
    employer: Optional[str] = None,
    employer_industry: Optional[str] = None,
    employer_country: Optional[str] = None,
    employer_min_employees: Optional[int] = None,
    employer_max_employees: Optional[int] = None,
    job_category: Optional[str] = None,
    job_location: Optional[str] = None,
    current: bool = True,
    school: Optional[str] = None,
    school_location: Optional[str] = None,
    major: Optional[str] = None,
    degree: Optional[str] = None,
    skill: Optional[List[str]] = None,
    language: Optional[str] = None,
    city: Optional[Union[str, List[str]]] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    nationality: Optional[str] = None,
    gender: Optional[str] = None,
    min_net_worth: Optional[float] = None,
    sort: Optional[Sort] = None,
) -> str:
    """employer_industry, job_category, language and gender must already be exact taxonomy/enum values."""
    clauses = ["type:Person"]
    if name:
        names = [name] if isinstance(name, str) else list(name)
        clauses.append(or_clause("name", names, strict=True))

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
    if employer_max_employees is not None:
        employment.append(compare("employer.nbEmployees", "<=", employer_max_employees))
    if job_category:
        employment.append(clause("categories.name", job_category))
    if job_location:
        employment.append(place_clause("location", job_location))
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
    if school_location:
        education.append(place_clause("location", school_location))
    clauses.append(subquery("educations", education))

    if skill:
        clauses.append(or_clause("skills.name", skill))
    if language:
        clauses.append(clause("languages", language))
    for level, value in (("city", city), ("region", region), ("country", country)):
        if value:
            values = [value] if isinstance(value, str) else list(value)
            clauses.append(or_clause(f"location.{level}.name", values))
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


@mcp.tool(name="search_people", title="Search People", description=DESCRIPTION, annotations=READ_ONLY)
async def search_people(
    name: Annotated[Optional[Union[str, List[str]]], "Person name(s), exact"] = None,
    title: Annotated[Optional[List[str]], "Job titles (OR); C-suite expanded"] = None,
    employer: Annotated[Optional[str], "Employer name"] = None,
    employer_industry: Annotated[Optional[str], "Employer's industry; free text ok"] = None,
    employer_employees: Annotated[Optional[str], "Employer headcount range, e.g. '<=50'"] = None,
    employer_country: Annotated[Optional[str], "Employer HQ country"] = None,
    job_category: Annotated[Optional[str], "Occupation group, e.g. 'Business', 'Religion'"] = None,
    job_location: Annotated[Optional[str], "City or country where the job is"] = None,
    current: Annotated[bool, "False: include past jobs"] = True,
    school: Annotated[Optional[str], "Institution name"] = None,
    school_location: Annotated[Optional[str], "City or country of the school"] = None,
    major: Annotated[Optional[str], "Field of study"] = None,
    degree: Annotated[Optional[str], "Degree, e.g. 'MBA'"] = None,
    skill: Annotated[Optional[List[str]], "Skills (OR)"] = None,
    language: Annotated[Optional[str], "Language spoken"] = None,
    city: Annotated[Optional[Union[str, List[str]]], "Residence city or cities"] = None,
    region: Annotated[Optional[str], "Residence state/region"] = None,
    country: Annotated[Optional[str], "Residence country"] = None,
    nationality: Annotated[Optional[str], "Nationality as country name"] = None,
    gender: Annotated[Optional[str], "Gender"] = None,
    net_worth: Annotated[Optional[str], "Minimum net worth, e.g. '1B'"] = None,
    sort: Annotated[Optional[Sort], "Only if ordering is the question"] = None,
    leadership_of: Annotated[Optional[str], "Company domain or name: its CEO and founders"] = None,
    size: Annotated[int, "Max rows"] = 10,
    offset: Annotated[int, "Rows to skip"] = 0,
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
    if job_category:
        resolved = await resolve_value("EmploymentCategory", job_category)
        if resolved.value is None:
            if resolved.candidates:
                return {"dql": None, "candidates": {"job_category": resolved.candidates}, "notes": [resolved.note]}
            raise ToolError(resolved.note)
        job_category = resolved.value
        if resolved.note:
            notes.append(resolved.note)
    for label, kind_name in (("gender", "Gender"), ("language", "Language")):
        value = gender if label == "gender" else language
        if value:
            resolved = await resolve_value(kind_name, value, kind="enum")
            if resolved.value is None:
                if resolved.candidates:
                    return {"dql": None, "candidates": {label: resolved.candidates}, "notes": [resolved.note]}
                raise ToolError(resolved.note)
            if label == "gender":
                gender = resolved.value
            else:
                language = resolved.value
    employer_min, employer_max = parse_range(employer_employees, "employer_employees", integer=True)
    min_net_worth, _ = parse_range(net_worth, "net_worth")

    query = build_people_query(
        name=name, title=title, employer=employer, employer_industry=employer_industry, employer_country=employer_country,
        employer_min_employees=employer_min, employer_max_employees=employer_max, job_category=job_category,
        job_location=job_location, current=current, school=school, school_location=school_location, major=major,
        degree=degree, skill=skill, language=language, city=city, region=region, country=country,
        nationality=nationality, gender=gender, min_net_worth=min_net_worth, sort=sort,
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
