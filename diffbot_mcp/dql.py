"""DQL execution, default column specs, and the cached ontology shared by every Knowledge Graph tool."""

import asyncio
import csv
import io
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastmcp.exceptions import ToolError

from .api import request, resolve_token

DQL_ENDPOINT = "https://kg.diffbot.com/kg/v3/dql"
ONTOLOGY_ENDPOINT = "https://kg.diffbot.com/kg/ontology"
ONTOLOGY_TTL_SECONDS = 86400
PROBE_CONCURRENCY = 8

# A full DQL entity record is ~75kb, so rows are pulled through the csv export with a
# column spec. These are the defaults per entity type, mirroring the specs the
# diffbot-skills use; the caller can override them with the fields parameter.
PLACE_FIELDS = (
    "name,Place;population,Population;placeType,Type;location.region.name,Region;"
    "location.country.name,Country;importance,Importance;id,Id"
)
DEFAULT_FIELDS: Dict[str, str] = {
    "Organization": (
        "name,Company;descriptors,Description;nbEmployees,Employees;revenue.value,Revenue;"
        "revenue.currency,Currency;location.city.name,City;location.country.name,Country;"
        "homepageUri,Website;isPublic,Public;id,Id"
    ),
    "Person": (
        "name,Name;$.employments[0].title,Title;$.employments[0].employer.name,Employer;"
        "location.city.name,City;location.country.name,Country;linkedInUri,LinkedIn;id,Id"
    ),
    "Article": (
        "date.str,Date;title,Title;siteName,Publisher;author,Author;sentiment,Sentiment;"
        "pageUrl,URL;summary,Summary;id,Id"
    ),
    "Product": "name,Name;brand,Brand;category,Category;offerPrice,Price;summary,Summary;id,Id",
    "Investment": (
        "investee.name,Company;investment.series,Round;investment.amount.value,Amount;"
        "investment.amount.currency,Currency;investment.date.str,Date;"
        "investment.investors.name,Lead Investor;id,Id"
    ),
    "Transaction": (
        "name,Name;payee.name,Payee;payers.name,Payer;amount.value,Amount;amount.currency,Currency;"
        "date.str,Date;id,Id"
    ),
    "*": "id,Id;name,Name;description,Description",
}
for _place_type in ("Place", "City", "Subregion", "Region", "Country", "AdministrativeArea"):
    DEFAULT_FIELDS[_place_type] = PLACE_FIELDS

TYPE_PATTERN = re.compile(r"\btype:([A-Za-z]+)")
# The csv export renders dates as d2026-07-23 and large numbers as 3.0E8.
DATE_VALUE = re.compile(r"^d(\d{4}-\d{2}-\d{2}.*)$")
SCI_NOTATION = re.compile(r"^-?\d+(\.\d+)?E[+-]?\d+$")


def query_type(query: str) -> Optional[str]:
    match = TYPE_PATTERN.search(query)
    return match.group(1) if match else None


def default_fields(query: str) -> str:
    return DEFAULT_FIELDS.get(query_type(query) or "", DEFAULT_FIELDS["*"])


def clean_value(value: str) -> str:
    match = DATE_VALUE.match(value)
    if match:
        return match.group(1)
    if SCI_NOTATION.match(value):
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    return value


def clean_row(row: Dict[str, str]) -> Dict[str, str]:
    return {column: clean_value(value) for column, value in row.items() if value}


async def dql_request(params: dict, as_text: bool = False) -> Any:
    return await request(DQL_ENDPOINT, params={"token": resolve_token(), **params}, as_text=as_text)


async def hits(query: str) -> int:
    return (await dql_request({"query": query, "size": 0})).get("hits", 0)


async def probe(queries: List[str]) -> List[dict]:
    """Hit counts for several queries in parallel; a failing query reports its error instead of failing the batch."""
    semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

    async def one(query: str) -> dict:
        if "similarTo(" in query:
            return {"query": query, "hits": None, "error": "similarTo cannot be probed: hits mirrors the requested size, so a size 0 probe always reports 0. Validate with a small export instead."}
        async with semaphore:
            try:
                return {"query": query, "hits": await hits(query)}
            except ToolError as error:
                return {"query": query, "hits": None, "error": str(error)}

    return list(await asyncio.gather(*(one(query) for query in queries)))


def is_facet(query: str) -> bool:
    return "facet:" in query or "facet[" in query


async def run(
    query: str,
    *,
    size: int = 10,
    offset: int = 0,
    fields: Optional[str] = None,
    format: str = "csv",
    hits_only: bool = False,
    bare_type_check: bool = False,
) -> dict:
    """Execute a DQL query and shape the response: a count, facet buckets, csv rows, or json entities."""
    if hits_only or size < 1:
        return {"dql": query, "hits": await hits(query)}

    notes: List[str] = []

    # facet queries answer with aggregate buckets rather than entities, and the csv
    # export is empty for them, so they are read from the json response instead
    if is_facet(query):
        result = await dql_request({"query": query, "size": max(size, 1)})
        return {
            "dql": query,
            "hits": result.get("hits", 0),
            "facet": True,
            "results": [{
                "value": bucket.get("value"),
                "count": bucket.get("count"),
                "query": bucket.get("callbackQuery"),
            } for bucket in (result.get("data") or [])[:size]],
        }

    # similarTo returns exactly `size` rows ranked by similarity and reports hits equal
    # to the size requested, so there is no meaningful total to fetch
    similar = "similarTo(" in query
    if similar:
        notes.append("similarTo returns a ranked list of exactly `size` rows; there is no total hit count. Ask for a larger size to go further down the ranking.")

    tasks: Dict[str, Any] = {}
    if not similar:
        tasks["count"] = dql_request({"query": query, "size": 0})
    entity_type = query_type(query)
    # an unknown field path is silently ignored by the API and returns the unfiltered
    # type count, so the bare count is fetched alongside to make that visible. Article
    # is skipped: an unfiltered probe over the article index times out.
    if bare_type_check and not similar and entity_type and entity_type != "Article" and query.strip() != f"type:{entity_type}":
        tasks["bare"] = dql_request({"query": f"type:{entity_type}", "size": 0})

    page = {"query": query, "size": size}
    if offset:
        page["from"] = offset
    if format == "json":
        tasks["data"] = dql_request(page)
    else:
        tasks["data"] = dql_request({**page, "format": "csv", "exportspec": fields or default_fields(query)}, as_text=True)

    values = await asyncio.gather(*tasks.values())
    outcome = dict(zip(tasks.keys(), values))

    total = None if similar else outcome["count"].get("hits", 0)
    if "bare" in outcome and total is not None and total == outcome["bare"].get("hits", -1):
        notes.append("Hit count equals the unfiltered type count: a filter path was probably ignored. Confirm field names with dql_ontology.")

    if format == "json":
        results = [record.get("entity") or record for record in (outcome["data"].get("data") or [])]
    else:
        results = [clean_row(row) for row in csv.DictReader(io.StringIO(outcome["data"]))]

    response = {
        "dql": query,
        "hits": total,
        "offset": offset,
        "returned": len(results),
        "results": results,
    }
    if notes:
        response["notes"] = notes
    return response


# --- ontology ---------------------------------------------------------------------

_ontology_cache: Dict[str, Any] = {}
_ontology_lock = asyncio.Lock()


def _ontology_fresh() -> bool:
    return bool(_ontology_cache.get("data")) and time.time() - _ontology_cache.get("fetched", 0) < ONTOLOGY_TTL_SECONDS


async def get_ontology() -> dict:
    """The ~700kb ontology changes rarely, so it is fetched once per process per day. The lock keeps concurrent first calls from downloading it twice."""
    if _ontology_fresh():
        return _ontology_cache["data"]
    async with _ontology_lock:
        if _ontology_fresh():
            return _ontology_cache["data"]
        data = await request(ONTOLOGY_ENDPOINT)
        _ontology_cache["data"] = data
        _ontology_cache["fetched"] = time.time()
        return data


def format_field(name: str, meta: dict) -> dict:
    field_type = meta.get("type", "?")
    if field_type == "LinkedEntity":
        linked = meta.get("leType") or []
        if linked:
            field_type = f"LinkedEntity ({linked[0]})"
    result = {"field": name, "type": field_type}
    flags = [flag for flag in ("isList", "isComposite", "isEnum") if meta.get(flag)]
    if flags:
        result["flags"] = flags
    if meta.get("description"):
        result["description"] = meta["description"]
    return result


def ontology_names(ontology: dict, kind: str) -> List[str]:
    return sorted(ontology.get(kind, {}).keys())


def ontology_fields(ontology: dict, name: str, pattern: Optional[re.Pattern] = None) -> List[dict]:
    container = ontology.get("types", {}).get(name) or ontology.get("composites", {}).get(name)
    if container is None:
        raise ToolError(f"'{name}' is not a known entity type or composite. Use action 'types' or 'composites' to list the valid names.")
    return [
        format_field(field_name, meta)
        for field_name, meta in (container.get("fields") or {}).items()
        if not meta.get("isDeprecated") and (pattern is None or pattern.search(field_name))
    ]


def taxonomy_values(ontology: dict, name: str, pattern: Optional[re.Pattern] = None) -> List[str]:
    taxonomy = ontology.get("taxonomies", {}).get(name)
    if taxonomy is None:
        raise ToolError(f"'{name}' is not a known taxonomy. Use action 'taxonomies' to list the valid names.")
    values: List[str] = []

    def walk(node: dict) -> None:
        value = node.get("name")
        if value and (pattern is None or pattern.search(value)):
            values.append(value)
        for child in node.get("children") or []:
            walk(child)

    for category in taxonomy.get("categories") or []:
        walk(category)
    return values


def enum_values(ontology: dict, name: str) -> List[str]:
    enum = ontology.get("enums", {}).get(name)
    if enum is None:
        raise ToolError(f"'{name}' is not a known enum. Use action 'enums' to list the valid names.")
    return list(enum.get("values") or [])


def find_named(ontology: dict, pattern: re.Pattern) -> List[str]:
    found = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            value = node.get("name")
            if isinstance(value, str) and pattern.search(value):
                found.add(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(ontology)
    return rank_names(found, pattern)


def rank_names(names, pattern: re.Pattern) -> List[str]:
    """Whole-name match first, then prefix, then word-start, then substring; shorter names first within a tier."""
    def key(name: str):
        match = pattern.search(name)
        if match is None:
            return (4, len(name), name)
        if match.start() == 0 and match.end() == len(name):
            tier = 0
        elif match.start() == 0:
            tier = 1
        elif not name[match.start() - 1].isalnum():
            tier = 2
        else:
            tier = 3
        return (tier, len(name), name)
    return sorted(set(names), key=key)


@dataclass
class Resolved:
    """Outcome of matching free text against a taxonomy or enum."""
    value: Optional[str]
    candidates: List[str] = field(default_factory=list)
    note: Optional[str] = None


MAX_CANDIDATES = 20

# Words that carry no meaning for matching a taxonomy value: "loan companies" should match "Mortgage And Loans Lenders".
_FILLER = {"and", "or", "of", "the", "a", "an", "in", "for", "company", "companies", "corporation", "corporations",
           "firm", "firms", "organization", "organizations", "business", "businesses", "industry"}


def _tokens(text: str) -> List[str]:
    out = []
    for token in re.split(r"[^a-z0-9]+", text.lower()):
        if not token or token in _FILLER:
            continue
        out.append(token[:-1] if len(token) > 3 and token.endswith("s") else token)
    return out


def _initials(value: str) -> str:
    return "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", value)).lower()


def rank_values(values: List[str], text: str) -> List[str]:
    """Taxonomy values that plausibly mean `text`, best first, from generic rules only.

    Tiers: exact (case-insensitive) > substring > every content token present > acronym of the value's words
    ("SaaS" -> "Software As A Service Companies"). Within a tier shorter values come first since they are the
    broader category. Returns [] when nothing matches.
    """
    lowered = text.strip().lower()
    if not lowered:
        return []
    exact = [v for v in values if v.lower() == lowered]
    if exact:
        return exact
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    short = len(compact) <= 4 and " " not in lowered
    # a short query like "EV" must match a whole word, or "DevOps" and "Beverage" would come back
    word = re.compile(rf"\b{re.escape(lowered)}\b")
    substring = {v for v in values if (word.search(v.lower()) if short else lowered in v.lower())}
    if substring:
        return sorted(substring, key=lambda v: (not v.lower().startswith(lowered), len(v), v))
    wanted = _tokens(text)
    if wanted:
        by_tokens = []
        for v in values:
            have = set(_tokens(v))
            if all(t in have for t in wanted):
                by_tokens.append(v)
        if by_tokens:
            return sorted(set(by_tokens), key=lambda v: (len(_tokens(v)), len(v), v))
    if 2 <= len(compact) <= 6 and " " not in lowered:
        acronym = [v for v in values if _initials(v).startswith(compact)]
        if acronym:
            return sorted(set(acronym), key=lambda v: (len(v), v))
    return []


async def resolve_value(name: str, text: str, kind: str = "taxonomy") -> Resolved:
    """Match text to one taxonomy or enum value, or return ranked candidates when several could be meant."""
    ontology = await get_ontology()
    values = taxonomy_values(ontology, name) if kind == "taxonomy" else enum_values(ontology, name)
    if text in values:
        return Resolved(text)
    matches = rank_values(values, text)
    if len(matches) == 1:
        return Resolved(matches[0], note=f"'{text}' resolved to the {name} value '{matches[0]}'")
    if matches:
        return Resolved(None, matches[:MAX_CANDIDATES], f"'{text}' could mean {len(matches)} {name} values; pass one of the candidates exactly")
    key = (_tokens(text) or [text.strip()])[0]
    return Resolved(None, [], f"'{text}' is not a {name} value; find the exact spelling with dql_ontology(action='taxonomy', name='{name}', search='{key}')")
