from typing import Annotated, List, Literal, Optional

from fastmcp.exceptions import ToolError

from ..app import mcp
from ..dql import DEFAULT_FIELDS, clean_value, resolve_value, run
from ..dql_builder import build, clause, compare, date_range, sort_clause, subquery, parse_range

DESCRIPTION = (
    "Funding rounds, investments, and acquisitions in the Diffbot Knowledge Graph by company, investor, acquirer, "
    "round series, amount, date, or the company's industry. Rows are deals (target, counterparty, amount, currency, "
    "date), not companies: deal flow, a company's funding history, an investor's activity, the largest acquisitions "
    "of a year. Returns rows plus the DQL it ran."
)

Kind = Literal["funding", "acquisitions", "any"]
Sort = Literal["newest", "largest"]
Facet = Literal["series", "investors", "amount"]

ACQUISITION_FIELDS = (
    "name,Target;acquiredBy.name,Acquirer;acquiredBy.amount.value,Amount;acquiredBy.amount.currency,Currency;"
    "acquiredBy.date.str,Date;categories.name,Industry;id,Id"
)
INDUSTRY_GET = "get:id,name,investments,categories"


def build_deals_query(
    *,
    kind: Kind = "funding",
    company: Optional[str] = None,
    investor: Optional[str] = None,
    acquirer: Optional[str] = None,
    series: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    currency: Optional[str] = "USD",
    since: Optional[str] = None,
    until: Optional[str] = None,
    industry: Optional[str] = None,
    sort: Optional[Sort] = None,
    facet: Optional[Facet] = None,
) -> tuple:
    """Return (dql, fields, mode) where mode is 'rows' or 'industry' (company-side json read). industry must already be an exact OrganizationCategory value."""
    if kind == "acquisitions":
        clauses = ["type:Organization", "isAcquired:true"]
        if company:
            clauses.append(clause("name", company, strict=True))
        if acquirer:
            clauses.append(clause("acquiredBy.name", acquirer))
        if investor:
            raise ToolError("investor does not apply to acquisitions; use acquirer.")
        if series:
            raise ToolError("series does not apply to acquisitions.")
        if industry:
            clauses.append(clause("categories.name", industry))
        if min_amount is not None:
            clauses.append(compare("acquiredBy.amount.value", ">=", min_amount))
        if max_amount is not None:
            clauses.append(compare("acquiredBy.amount.value", "<=", max_amount))
        if (min_amount is not None or max_amount is not None) and currency:
            clauses.append(clause("acquiredBy.amount.currency", currency))
        clauses.extend(date_range("acquiredBy.date", since, until))
        if facet:
            facet_field = {"investors": "acquiredBy.name", "amount": "acquiredBy.amount.value"}.get(facet)
            if not facet_field:
                raise ToolError("facet 'series' does not apply to acquisitions.")
            clauses.append(f"facet:{facet_field}")
        elif sort:
            clauses.append(sort_clause("acquiredBy.date" if sort == "newest" else "acquiredBy.amount.value"))
        return build(clauses), ACQUISITION_FIELDS, "rows"

    if kind == "funding" and industry:
        # investee is a bare LinkedEntity with no categories, so the industry lives on the
        # company; the round's conditions are co-constrained on one investment with {}
        round_conditions = []
        if series:
            round_conditions.append(clause("series", series))
        if investor:
            round_conditions.append(clause("investors.name", investor))
        if min_amount is not None:
            round_conditions.append(compare("amount.value", ">=", min_amount))
        if max_amount is not None:
            round_conditions.append(compare("amount.value", "<=", max_amount))
        if (min_amount is not None or max_amount is not None) and currency:
            round_conditions.append(clause("amount.currency", currency))
        round_conditions.extend(date_range("date", since, until))
        clauses = ["type:Organization", clause("categories.name", industry)]
        if company:
            clauses.append(clause("name", company, strict=True))
        clauses.append(subquery("investments", round_conditions) if round_conditions else "has:investments")
        if facet:
            raise ToolError("facet does not combine with industry; drop industry or facet.")
        if sort:
            clauses.append(sort_clause("investments.date" if sort == "newest" else "investments.amount.value"))
        return build(clauses), None, "industry"

    if kind == "funding":
        clauses = ["type:Investment"]
        company_field, investor_field, amount_field, date_field = "investee.name", "investment.investors.name", "investment.amount", "investment.date"
    else:
        clauses = ["type:Transaction"]
        company_field, investor_field, amount_field, date_field = "payee.name", "payers.name", "amount", "date"
        if series:
            raise ToolError("series applies to kind 'funding' only.")
        if industry:
            raise ToolError("industry applies to kind 'funding' or 'acquisitions'.")

    if company:
        clauses.append(clause(company_field, company))
    if investor or acquirer:
        clauses.append(clause(investor_field, investor or acquirer))
    if series:
        clauses.append(clause("investment.series", series))
    if min_amount is not None:
        clauses.append(compare(f"{amount_field}.value", ">=", min_amount))
    if max_amount is not None:
        clauses.append(compare(f"{amount_field}.value", "<=", max_amount))
    if (min_amount is not None or max_amount is not None) and currency:
        clauses.append(clause(f"{amount_field}.currency", currency))
    clauses.extend(date_range(date_field, since, until))

    if len(clauses) == 1:
        raise ToolError("search_deals needs at least one filter.")

    if facet:
        facet_field = {"series": "investment.series", "investors": investor_field, "amount": f"{amount_field}.value"}[facet]
        if kind == "any" and facet == "series":
            raise ToolError("facet 'series' applies to kind 'funding' only.")
        clauses.append(f"facet:{facet_field}")
    elif sort:
        clauses.append(sort_clause(date_field if sort == "newest" else f"{amount_field}.value"))
    fields = DEFAULT_FIELDS["Investment" if kind == "funding" else "Transaction"]
    return build(clauses), fields, "rows"


def plain_number(value):
    """json amounts arrive as floats; render integral ones as ints so rows match the csv form."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def investment_matches(investment: dict, *, series, investor, min_amount, max_amount, currency, since, until) -> bool:
    amount = investment.get("amount") or {}
    value = amount.get("value")
    if min_amount is not None and (value is None or value < min_amount):
        return False
    if max_amount is not None and (value is None or value > max_amount):
        return False
    if (min_amount is not None or max_amount is not None) and currency and amount.get("currency") and amount["currency"] != currency:
        return False
    if series and series.lower() not in (investment.get("series") or "").lower():
        return False
    if investor and not any(investor.lower() in (i.get("name") or "").lower() for i in investment.get("investors") or []):
        return False
    date = clean_value((investment.get("date") or {}).get("str") or "")[:10]
    if since and (not date or date < since):
        return False
    if until and (not date or date > until):
        return False
    return True


def render_company_rounds(entity: dict, **conditions) -> List[dict]:
    rows = []
    for investment in entity.get("investments") or []:
        if not investment_matches(investment, **conditions):
            continue
        amount = investment.get("amount") or {}
        row = {
            "Company": entity.get("name"),
            "Round": investment.get("series"),
            "Amount": plain_number(amount.get("value")),
            "Currency": amount.get("currency"),
            "Date": clean_value((investment.get("date") or {}).get("str") or "")[:10] or None,
            "Investors": ", ".join(i.get("name") for i in investment.get("investors") or [] if i.get("name")) or None,
            "Company Id": entity.get("id"),
        }
        rows.append({key: value for key, value in row.items() if value is not None and value != ""})
    return rows


@mcp.tool(name="search_deals", description=DESCRIPTION)
async def search_deals(
    kind: Annotated[Kind, "funding | acquisitions | any"] = "funding",
    company: Annotated[Optional[str], "Company raising or acquired"] = None,
    investor: Annotated[Optional[str], "Investor name"] = None,
    acquirer: Annotated[Optional[str], "Acquirer name"] = None,
    series: Annotated[Optional[str], "Round, e.g. 'Series A'"] = None,
    amount: Annotated[Optional[str], "Deal size range, e.g. '50M+', '1M-10M'"] = None,
    currency: Annotated[Optional[str], "Currency of amount"] = "USD",
    since: Annotated[Optional[str], "Earliest date, YYYY-MM-DD"] = None,
    until: Annotated[Optional[str], "Latest date, YYYY-MM-DD"] = None,
    industry: Annotated[Optional[str], "Company's industry; free text ok"] = None,
    sort: Annotated[Optional[Sort], "Only if ordering is the question"] = None,
    facet: Annotated[Optional[Facet], "Bucket by series, investors, or amount"] = None,
    size: Annotated[int, "Max rows or buckets"] = 10,
    offset: Annotated[int, "Rows to skip"] = 0,
) -> dict:
    min_amount, max_amount = parse_range(amount, "amount")
    notes: List[str] = []
    if industry:
        resolved = await resolve_value("OrganizationCategory", industry)
        if resolved.value is None:
            if resolved.candidates:
                return {"dql": None, "candidates": {"industry": resolved.candidates}, "notes": [resolved.note]}
            raise ToolError(resolved.note)
        industry = resolved.value
        if resolved.note:
            notes.append(resolved.note)

    query, fields, mode = build_deals_query(
        kind=kind, company=company, investor=investor, acquirer=acquirer, series=series, min_amount=min_amount,
        max_amount=max_amount, currency=currency, since=since, until=until, industry=industry, sort=sort, facet=facet,
    )

    if mode == "industry":
        result = await run(f"{query} {INDUSTRY_GET}", size=size, offset=offset, format="json", bare_type_check=True)
        conditions = dict(series=series, investor=investor, min_amount=min_amount, max_amount=max_amount, currency=currency, since=since, until=until)
        rows = []
        for entity in result.get("results") or []:
            rows.extend(render_company_rounds(entity, **conditions))
        result["dql"] = query
        result["results"] = rows
        result["returned"] = len(rows)
        notes.append("hits counts companies in the industry with a matching round; results list each matching round per company.")
    else:
        result = await run(query, size=size, offset=offset, fields=fields, bare_type_check=True)

    if notes:
        result["notes"] = result.get("notes", []) + notes
    return result
