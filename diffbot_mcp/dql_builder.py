"""Pure helpers for assembling DQL strings. No I/O, so the typed tools' queries are unit-testable."""

import re
import unicodedata
from typing import Iterable, List, Optional

from fastmcp.exceptions import ToolError

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RADIUS_PATTERN = re.compile(r"^\d+(\.\d+)?\s?(mi|km)$")

# Titles are free text and an abbreviation is not a substring of its expansion, so a
# C-suite search that omits either form silently under-counts by ~5x. Board seats are
# titled "Director" far more often than "Board Member" (904 vs 5 at Nvidia).
TITLE_EXPANSIONS = {
    "ceo": ["Chief Executive Officer", "CEO"],
    "chief executive officer": ["Chief Executive Officer", "CEO"],
    "cto": ["Chief Technology Officer", "CTO"],
    "chief technology officer": ["Chief Technology Officer", "CTO"],
    "cfo": ["Chief Financial Officer", "CFO"],
    "chief financial officer": ["Chief Financial Officer", "CFO"],
    "coo": ["Chief Operating Officer", "COO"],
    "chief operating officer": ["Chief Operating Officer", "COO"],
    "cio": ["Chief Information Officer", "CIO"],
    "chief information officer": ["Chief Information Officer", "CIO"],
    "cmo": ["Chief Marketing Officer", "CMO"],
    "chief marketing officer": ["Chief Marketing Officer", "CMO"],
    "board member": ["Board Member", "Board of Directors", "Director"],
    "board of directors": ["Board Member", "Board of Directors", "Director"],
    "board": ["Board Member", "Board of Directors", "Director"],
}


def quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def clause(field: str, value: str, strict: bool = False) -> str:
    return f"{'strict:' if strict else ''}{field}:{quote(value)}"


def dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        value = str(value).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def or_clause(field: str, values: Iterable[str], strict: bool = False) -> str:
    values = dedupe(values)
    if not values:
        return ""
    if len(values) == 1:
        return clause(field, values[0], strict)
    return f"{'strict:' if strict else ''}{field}:or({','.join(quote(v) for v in values)})"


def subquery(field: str, clauses: Iterable[str]) -> str:
    """field.{a b c}: co-constrain several conditions on the same nested list object."""
    inner = " ".join(c for c in clauses if c)
    return f"{field}.{{{inner}}}" if inner else ""


def number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def compare(field: str, operator: str, value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{field}{operator}{number(value)}"
    return f"{field}{operator}{quote(str(value))}"


def validate_date(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not DATE_PATTERN.match(value):
        raise ToolError(f"{name} must be a full date in YYYY-MM-DD form, got '{value}'")
    return value


def date_range(field: str, since: Optional[str], until: Optional[str]) -> List[str]:
    clauses = []
    if since:
        clauses.append(compare(field, ">=", validate_date(since, "since")))
    if until:
        clauses.append(compare(field, "<=", validate_date(until, "until")))
    return clauses


def sort_clause(field: str, descending: bool = True) -> str:
    return f"{'revSortBy' if descending else 'sortBy'}:{field}"


def near_clause(anchor: str, radius: Optional[str] = None) -> str:
    if radius:
        radius = radius.strip().replace(" ", "")
        if not RADIUS_PATTERN.match(radius):
            raise ToolError(f"radius must be a number followed by mi or km, e.g. '30mi', got '{radius}'")
        return f"near(type:Place name:{quote(anchor)}, {radius})"
    return f"near(type:Place name:{quote(anchor)})"


def expand_titles(titles: Iterable[str]) -> List[str]:
    expanded: List[str] = []
    for title in titles:
        expanded.extend(TITLE_EXPANSIONS.get(title.strip().lower(), [title]))
    return dedupe(expanded)


def ascii_variant(text: str) -> Optional[str]:
    """The ASCII spelling of an accented name, or None when it is already ASCII. Diacritics are not normalized in the KG and coverage of each spelling is inconsistent."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return folded if folded and folded != text else None


def name_variants(text: str) -> List[str]:
    variant = ascii_variant(text)
    return [text, variant] if variant else [text]


def looks_like_domain(text: str) -> bool:
    text = text.strip()
    return " " not in text and "." in text and not text.endswith(".")


def build(clauses: Iterable[str]) -> str:
    return " ".join(c for c in clauses if c)
