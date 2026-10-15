"""Model-in-the-loop routing eval: real user questions through an isolated `claude -p` session
that sees only this MCP server, asserting which tool the model called and what DQL actually ran.

This is the only test with a model in the loop. The unit tests prove the builders, the smoke test
proves the tools against the live APIs; this proves the tool descriptions and prompts actually
steer a model to the right call. It costs model tokens; Haiku is the default because it is the
cheapest and the most sensitive to schema quality, so if it routes correctly the larger models will.

    env/bin/python tests/eval_routing.py                          # every case, Haiku, 4 in parallel
    env/bin/python tests/eval_routing.py --entity Organization    # one entity type from the CSV
    env/bin/python tests/eval_routing.py --only csv_46 --show-calls
    env/bin/python tests/eval_routing.py --model sonnet --report out.json

Cases come from two places: CASES below (hand-written, with argument predicates) and
tests/e2e_dql_examples.csv (curated prompt -> DQL pairs). A CSV case passes when the model
used the typed tool for that entity type or fell back to dql, and the DQL that ran carries every quoted
value and numeric bound of the curated DQL. Exact string equality is not required: the typed tools emit
categories.{name:X isPrimary:true} and strict:name where the curated queries use the loose forms.

Needs the `claude` CLI on PATH and a Diffbot token where api.resolve_token finds it.
"""

import argparse
import csv
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diffbot_mcp.api import resolve_token  # noqa: E402
from diffbot_mcp.dql_builder import parse_range  # noqa: E402

SERVER_NAME = "diffbot"
PYTHON = pathlib.Path(sys.executable)
CASE_TIMEOUT_SECONDS = 300
DEFAULT_MODEL = "haiku"
CSV_PATH = ROOT / "tests" / "e2e_dql_examples.csv"

HARNESS_TOOLS = {"ToolSearch"}

# entity_type in the CSV -> the typed tool that should handle it; dql is always an accepted fallback
TYPED_TOOL = {
    "organization": "search_organizations",
    "person": "search_people",
    "article": "search_news",
    "investment": "search_deals",
    "city": "search_places", "country": "search_places", "place": "search_places",
    "extract": "extract",
    "web_search": "search_web",
}
DQL_TOOLS = {"search_organizations", "search_people", "search_news", "search_deals", "search_places", "dql"}


def tool_name(name: str) -> str:
    prefix = f"mcp__{SERVER_NAME}__"
    return name[len(prefix):] if name.startswith(prefix) else name


def fold(text: str) -> str:
    """Case- and accent-insensitive comparison key."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def contains_ci(values: Any, needle: str) -> bool:
    if values is None:
        return False
    if isinstance(values, str):
        values = [values]
    return any(fold(needle) in fold(str(v)) for v in values)


# --- hand-written cases ----------------------------------------------------------------------

Predicate = Callable[[dict], Optional[str]]


def expect(key: str, value: Any) -> Predicate:
    def check(args: dict) -> Optional[str]:
        got = args.get(key)
        ok = float(got) == float(value) if isinstance(got, (int, float)) and isinstance(value, (int, float)) else got == value
        return None if ok else f"{key}={got!r}, expected {value!r}"
    return check


def expect_contains(key: str, needle: str) -> Predicate:
    def check(args: dict) -> Optional[str]:
        return None if contains_ci(args.get(key), needle) else f"{key}={args.get(key)!r} does not mention {needle!r}"
    return check


def expect_range(key: str, low: float, high: float) -> Predicate:
    def check(args: dict) -> Optional[str]:
        raw = args.get(key)
        if raw is None:
            return f"{key} not set"
        try:
            got = parse_range(str(raw), key)
        except Exception as error:
            return f"{key}={raw!r} did not parse: {error}"
        return None if got == (low, high) else f"{key}={raw!r} parsed to {got}, expected {(low, high)}"
    return check


@dataclass
class Case:
    name: str
    query: str
    tool: str                                  # the tool that should handle it
    args: List[Predicate] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    allow_fallback: Tuple[str, ...] = ()       # other tools that also count as correct routing
    expected_dql: Optional[str] = None         # curated DQL whose values and bounds must appear in the DQL that ran
    entity: str = ""
    note: str = ""


CASES: List[Case] = [
    Case(
        name="ma_software_revenue_band",
        query="Find software companies in Massachusetts with revenue between $10 million and $75 million",
        tool="search_organizations",
        entity="Organization",
        args=[
            expect_contains("industry", "software"),
            expect_contains("region", "Massachusetts"),
            expect_range("revenue", 10_000_000, 75_000_000),
        ],
        forbidden=["dql", "search_web"],
        note="A bounded revenue band must go through the typed tool, not fall back to raw DQL or web search.",
    ),
]


# --- curated CSV cases -----------------------------------------------------------------------

def load_csv_cases(path: pathlib.Path) -> List[Case]:
    cases: List[Case] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            entity = (row.get("entity_type") or "").strip()
            key = entity.lower()
            if key not in TYPED_TOOL:
                continue  # unmapped types (Product, Movie, ...) and blank rows are not routing cases yet
            try:
                arguments = json.loads(row["arguments"])
            except json.JSONDecodeError:
                continue
            tool = TYPED_TOOL[key]
            name = f"csv_{row['id'].strip()}"
            if "dql_query" in arguments:
                queries = arguments["dql_query"]
                expected = queries[0] if isinstance(queries, list) and len(queries) == 1 else None
                if expected is None:
                    continue  # multi-query examples need a judgement this harness does not make
                # any DQL tool is acceptable routing as long as the query that ran has the right type: and content
                cases.append(Case(name=name, query=row["text"], tool=tool, allow_fallback=tuple(sorted(DQL_TOOLS - {tool})), expected_dql=expected, entity=entity))
            elif "page_url" in arguments:
                urls = arguments["page_url"]
                url = urls[0] if isinstance(urls, list) and urls else urls if isinstance(urls, str) else ""
                if not url:
                    continue
                cases.append(Case(name=name, query=row["text"], tool=tool, entity=entity,
                                  args=[expect_contains("url", url.split("//")[-1].rstrip("/"))]))
            elif "text" in arguments:
                cases.append(Case(name=name, query=row["text"], tool=tool, entity=entity))
    return cases


LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')
NUMERIC = re.compile(r"([A-Za-z_.]+)\s*(>=|<=|>|<)\s*([0-9][0-9.]*)(?![0-9-])")
DATE_BOUND = re.compile(r'([A-Za-z_.]*[Dd]ate[A-Za-z_.]*)\s*(>=|<=|>|<)\s*"?(\d{4})(?:-\d{2}-\d{2})?"?')


def dql_facts(dql: str) -> Dict[str, set]:
    """The checkable content of a DQL string: quoted values, numeric bounds, and the years of date bounds."""
    is_date = re.compile(r"^\d{4}(-\d{2}-\d{2})?$")
    literals = {fold(v.strip().rstrip("'")) for v in LITERAL.findall(dql) if v.strip() and not is_date.match(v.strip())}
    numeric = set()
    for field_name, op, value in NUMERIC.findall(dql):
        if field_name.split(".")[-1] in ("value", "nbEmployees", "amount", "capitalization", "population"):
            numeric.add((field_name.split(".")[-1] if field_name.endswith(".value") else field_name, op, float(value)))
    years = set()
    for field_name, op, year in DATE_BOUND.findall(dql):
        # an exclusive upper bound on Jan 1 is the inclusive end of the prior year: <"2023-01-01" == <="2022-12-31"
        if op == "<" and re.search(rf'{re.escape(field_name)}\s*<\s*"?{year}-01-01', dql):
            year = str(int(year) - 1)
        years.add((field_name.split(".")[-1], year))
    return {"literals": literals, "numeric": numeric, "years": years}


def literal_present(value: str, actual_literals: set, actual_text: str = "") -> bool:
    """Substring match (quoted or anywhere in the query), else every content token (plural-insensitive) appears."""
    if any(value in h for h in actual_literals) or (actual_text and value in actual_text):
        return True
    tokens = [t.rstrip("s") for t in re.split(r"[^a-z0-9&]+", value) if len(t) >= 3]
    haystack = " ".join(actual_literals)
    return bool(tokens) and all(t in haystack for t in tokens)


def bound_present(field_name: str, op: str, value: float, actual: set) -> bool:
    """Same bound, allowing the integer-equivalent inclusive form: <N == <=N-1, >N == >=N+1."""
    short = field_name.split(".")[-1]
    equivalents = {(op, value)}
    if op == "<":
        equivalents.add(("<=", value - 1))
    elif op == ">":
        equivalents.add((">=", value + 1))
    elif op == "<=":
        equivalents.add(("<", value + 1))
    elif op == ">=":
        equivalents.add((">", value - 1))
    return any(h[0].endswith(short) and (h[1], h[2]) in equivalents for h in actual)


def dql_coverage(expected: str, actual: str, check_type: bool = True) -> List[str]:
    want, have = dql_facts(expected), dql_facts(actual)
    missing: List[str] = []
    want_type = re.match(r"type:(\w+)", expected)
    have_type = re.match(r"type:(\w+)", actual.strip())
    if check_type and want_type and (not have_type or have_type.group(1) != want_type.group(1)):
        missing.append(f"type:{want_type.group(1)} (ran type:{have_type.group(1) if have_type else '?'})")
    missing += [f'value "{v}"' for v in sorted(want["literals"]) if not literal_present(v, have["literals"], fold(actual))]
    for field_name, op, value in sorted(want["numeric"]):
        if not bound_present(field_name, op, value, have["numeric"]):
            missing.append(f"bound {field_name}{op}{value:g}")
    for field_name, year in sorted(want["years"]):
        if year not in actual:
            missing.append(f"year {year} on {field_name}")
    return missing


# --- running ---------------------------------------------------------------------------------

@dataclass
class Run:
    calls: List[dict]
    final_text: str
    cost_usd: Optional[float]
    duration_ms: Optional[int]
    turns: Optional[int]
    stderr: str
    model: Optional[str] = None


def mcp_config(server: pathlib.Path) -> str:
    return json.dumps({"mcpServers": {SERVER_NAME: {"command": str(PYTHON), "args": [str(server)]}}})


def run_query(query: str, model: str, server: pathlib.Path) -> Run:
    cmd = [
        "claude", "-p",
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
        "--mcp-config", mcp_config(server),
        "--tools", "",
        "--allowedTools", f"mcp__{SERVER_NAME}__*",
        "--model", model,
    ]
    env = dict(os.environ)
    env.setdefault("DIFFBOT_TOKEN", resolve_token())
    proc = subprocess.run(cmd, input=query, capture_output=True, text=True, timeout=CASE_TIMEOUT_SECONDS, cwd=ROOT, env=env)

    calls: List[dict] = []
    by_id: Dict[str, dict] = {}
    final_text = ""
    cost = duration = turns = model_used = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            model_used = event.get("model")
        elif kind == "assistant":
            for block in event["message"]["content"]:
                if block["type"] == "tool_use" and block["name"] not in HARNESS_TOOLS:
                    call = {"name": tool_name(block["name"]), "input": block.get("input") or {}, "result": None, "is_error": None}
                    calls.append(call)
                    by_id[block["id"]] = call
                elif block["type"] == "text":
                    final_text = block["text"]
        elif kind == "user":
            for block in event["message"]["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id") in by_id:
                    call = by_id[block["tool_use_id"]]
                    call["result"] = block.get("content")
                    call["is_error"] = bool(block.get("is_error"))
        elif kind == "result":
            cost = event.get("total_cost_usd")
            duration = event.get("duration_ms")
            turns = event.get("num_turns")
            if event.get("subtype") != "success":
                final_text = final_text or f"[{event.get('subtype')}] {event.get('result', '')}"
    return Run(calls, final_text, cost, duration, turns, proc.stderr, model_used)


def ran_dql(call: dict) -> Optional[str]:
    """The DQL a call actually executed: the dql tool's query argument, or the typed tool's reported dql."""
    if call["name"] == "dql":
        return call["input"].get("query")
    if call["name"] in DQL_TOOLS and call["result"]:
        for block in call["result"] if isinstance(call["result"], list) else [call["result"]]:
            text = block.get("text") if isinstance(block, dict) else str(block)
            try:
                return json.loads(text).get("dql")
            except (TypeError, ValueError, AttributeError):
                continue
    return None


def evaluate(case: Case, run: Run) -> Tuple[List[str], Optional[str]]:
    """Returns (errors, tool that handled it)."""
    if not run.calls:
        return [f"no MCP tool was called; model said: {run.final_text[:200]!r}"], None
    names = [c["name"] for c in run.calls]
    accepted = (case.tool,) + case.allow_fallback
    # a forbidden tool counts against routing only if the model reached for it before the right one
    first_right = next((i for i, n in enumerate(names) if n in accepted), len(names))
    errors = [f"called forbidden tool {bad} before {case.tool}" for bad in case.forbidden if bad in names[:first_right]]
    handled = [c for c in run.calls if c["name"] in accepted]
    if not handled:
        return errors + [f"never called {' or '.join(accepted)}; called {names}"], None
    first = handled[0]
    for predicate in case.args:
        problem = predicate(first["input"])
        if problem:
            errors.append(problem)
    if case.expected_dql:
        candidates = [d for d in (ran_dql(c) for c in handled) if d]
        if not candidates:
            errors.append("no DQL was run (tool errored or returned candidates only)")
        else:
            want_type = re.match(r"type:(\w+)", case.expected_dql)
            same_type = [d for d in candidates if want_type and d.strip().startswith(f"type:{want_type.group(1)}")]
            if any(c["name"] == case.tool for c in handled):
                # the typed tool for this entity decides its own query shape (leadership_of reads the Organization)
                own = [d for d in (ran_dql(c) for c in handled if c["name"] == case.tool) if d]
                same_type = same_type or own
            if not same_type:
                errors.append("DQL missing " + ", ".join(min((dql_coverage(case.expected_dql, d) for d in candidates), key=len)))
            else:
                own_tool = any(c["name"] == case.tool for c in handled)
                per_query = min((dql_coverage(case.expected_dql, d, check_type=not own_tool) for d in same_type), key=len)
                union = dql_coverage(case.expected_dql, " ".join(same_type), check_type=not own_tool)
                if union:
                    errors.append("DQL missing " + ", ".join(union))
                elif per_query:
                    pass  # covered only across several queries; counts as a pass, noted via the calls list
    if all(c["is_error"] for c in handled):
        errors.append(f"{first['name']} returned an error: {json.dumps(first['result'])[:200]}")
    if not run.final_text.strip():
        errors.append("model produced no final answer")
    used = first["name"] if first["name"] == case.tool else f"{first['name']} (fallback)"
    return errors, used


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", help="run only the named case (repeatable)")
    parser.add_argument("--entity", action="append", help="run only cases of this entity type, e.g. Organization (repeatable)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model alias or id to pass to claude (default {DEFAULT_MODEL})")
    parser.add_argument("--parallel", type=int, default=4, help="cases to run concurrently")
    parser.add_argument("--show-calls", action="store_true", help="print every tool call and the final answer")
    parser.add_argument("--report", type=pathlib.Path, help="write per-case results as JSON here")
    parser.add_argument("--server", type=pathlib.Path, default=ROOT / "diffbot_mcp_server.py",
                        help="server entry point to run over stdio; point at an older diffbot_mcp_server.py to compare routing")
    options = parser.parse_args()

    if not shutil.which("claude"):
        print("FAIL  the `claude` CLI is not on PATH", file=sys.stderr)
        return 2

    all_cases = CASES + (load_csv_cases(CSV_PATH) if CSV_PATH.exists() else [])
    selected = [c for c in all_cases if not options.only or c.name in options.only]
    if options.entity:
        wanted = {e.lower() for e in options.entity}
        selected = [c for c in selected if c.entity.lower() in wanted]
    if not selected:
        print(f"no cases match; known: {[c.name for c in all_cases]}", file=sys.stderr)
        return 2

    server = options.server.resolve()

    def one(case: Case) -> dict:
        try:
            run = run_query(case.query, options.model, server)
        except subprocess.TimeoutExpired:
            return {"case": case, "run": None, "errors": [f"timed out after {CASE_TIMEOUT_SECONDS}s"], "used": None}
        errors, used = evaluate(case, run)
        return {"case": case, "run": run, "errors": errors, "used": used}

    with ThreadPoolExecutor(max_workers=max(1, options.parallel)) as pool:
        results = list(pool.map(one, selected))

    failures = 0
    total_cost = 0.0
    models_seen = set()
    report = []
    for item in results:
        case, run, errors, used = item["case"], item["run"], item["errors"], item["used"]
        failures += bool(errors)
        status = "PASS" if not errors else "FAIL"
        if run:
            total_cost += run.cost_usd or 0.0
            models_seen.add(run.model or "unknown")
            seconds = (run.duration_ms or 0) / 1000
            print(f"{status}  {case.name:28} via {used or '-':32} {seconds:4.0f}s  {case.query[:70]}")
        else:
            print(f"{status}  {case.name:28} {errors[0]}")
        for error in errors:
            print(f"      - {error}")
        if run and (options.show_calls or errors):
            if case.expected_dql:
                print(f"      expected: {case.expected_dql}")
            for call in run.calls:
                dql = ran_dql(call)
                print(f"      > {call['name']}({json.dumps(call['input'])[:300]})" + ("  [error]" if call["is_error"] else ""))
                if dql:
                    print(f"        ran: {dql}")
            if options.show_calls:
                print("      answer:", run.final_text[:400].replace("\n", " "))
        report.append({
            "name": case.name, "entity": case.entity, "query": case.query, "status": status, "used": used, "errors": errors,
            "expected_dql": case.expected_dql, "ran_dql": [ran_dql(c) for c in run.calls] if run else [],
            "calls": [{"name": c["name"], "input": c["input"]} for c in run.calls] if run else [],
            "cost_usd": run.cost_usd if run else None, "turns": run.turns if run else None,
        })

    by_tool: Dict[str, int] = {}
    for item in results:
        by_tool[item["used"] or "none"] = by_tool.get(item["used"] or "none", 0) + 1
    print(f"\n{'PASS' if not failures else 'FAIL'}: {failures} failed of {len(selected)}, ${total_cost:.2f} total, model {', '.join(sorted(models_seen))}")
    print("routed via:", ", ".join(f"{k} x{v}" for k, v in sorted(by_tool.items(), key=lambda kv: -kv[1])))
    if options.report:
        options.report.write_text(json.dumps({"model": sorted(models_seen), "results": report}, indent=1))
        print(f"report: {options.report}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
