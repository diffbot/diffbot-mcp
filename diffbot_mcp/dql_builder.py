"""Pure helpers for assembling DQL strings. No I/O, so the typed tools' queries are unit-testable."""

import re
import unicodedata
from typing import Iterable, List, Optional, Tuple

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

_UNITS = {"k": 1e3, "m": 1e6, "b": 1e9}
_NUMBER = re.compile(r"^\$?([0-9][0-9,]*\.?[0-9]*)\s*([kmb])?$", re.IGNORECASE)


def parse_amount(text: str, name: str) -> float:
    """'10M' -> 10000000, '$1.5b' -> 1500000000, '50,000' -> 50000."""
    match = _NUMBER.match(text.strip())
    if not match:
        raise ToolError(f"{name}: cannot read '{text}'; use a number with an optional K/M/B suffix, e.g. '10M'.")
    value = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    return value * _UNITS.get(unit, 1)


def parse_range(text: Optional[str], name: str, parse=parse_amount) -> Tuple[Optional[float], Optional[float]]:
    """One range string -> (low, high). Forms: '10M-75M', '500+', '>=500', '>500', '<5000', '<=5000', '500' (exact: both bounds)."""
    if text is None:
        return None, None
    text = text.strip().replace(" ", "")
    if not text:
        return None, None
    for op in (">=", "<=", ">", "<"):
        if text.startswith(op):
            value = parse(text[len(op):], name)
            if op[0] == ">":
                return value, None
            return None, value
    if text.endswith("+"):
        return parse(text[:-1], name), None
    # split on a dash that is between two bounds, not a leading minus
    parts = re.split(r"(?<=[0-9a-zA-Z])-(?=[\$0-9])", text, maxsplit=1)
    if len(parts) == 2:
        low, high = parse(parts[0], name), parse(parts[1], name)
        if low > high:
            raise ToolError(f"{name}: low bound {parts[0]} is above high bound {parts[1]}.")
        return low, high
    value = parse(text, name)
    return value, value


def parse_year_or_date(text: str, name: str) -> str:
    """'2015' -> '2015' as-is for the caller to pad; full dates pass validate_date."""
    text = text.strip()
    if re.fullmatch(r"[0-9]{4}", text):
        return text
    return validate_date(text, name) or text


def parse_date_range(text: Optional[str], name: str) -> Tuple[Optional[str], Optional[str]]:
    """'2015-2020' -> ('2015-01-01', '2020-12-31'); '2019' -> that whole year; '>=2020-06-01' -> (that, None)."""
    if text is None or not text.strip():
        return None, None
    text = text.strip().replace(" ", "")
    def pad(value: Optional[str], end: bool) -> Optional[str]:
        if value is None:
            return None
        return f"{value}-12-31" if end and len(value) == 4 else f"{value}-01-01" if len(value) == 4 else value
    for op in (">=", "<=", ">", "<"):
        if text.startswith(op):
            value = parse_year_or_date(text[len(op):], name)
            return (pad(value, False), None) if op[0] == ">" else (None, pad(value, True))
    if text.endswith("+"):
        return pad(parse_year_or_date(text[:-1], name), False), None
    # year-year, or date-date (dates contain dashes, so split only on a dash followed by a 4-digit year)
    parts = re.split(r"(?<=[0-9])-(?=[0-9]{4}(?:-|$))", text, maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1]:
        low, high = parse_year_or_date(parts[0], name), parse_year_or_date(parts[1], name)
        return pad(low, False), pad(high, True)
    value = parse_year_or_date(text, name)
    return pad(value, False), pad(value, True)


def split_near(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """'Austin 30mi' -> ('Austin', '30mi'); 'Austin' -> ('Austin', None)."""
    if not text:
        return None, None
    match = re.match(r"^(.*?)[\s,]+([0-9]+(?:\.[0-9]+)?\s*(?:mi|miles|km|m))\.?$", text.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).replace(" ", "").replace("miles", "mi")
    return text.strip(), None
