"""Model-in-the-loop routing eval: real user questions through an isolated `claude -p` session
that sees only this MCP server, asserting which tool the model called and with what arguments.

This is the only test with a model in the loop. The unit tests prove the builders, the smoke test
proves the tools against the live APIs; this proves the tool descriptions and prompts actually
steer a model to the right call. It costs model tokens and takes roughly half a minute per case.

    env/bin/python tests/eval_routing.py                 # every case
    env/bin/python tests/eval_routing.py --only ma_software_revenue_band
    env/bin/python tests/eval_routing.py --show-calls    # print every tool call the model made

Needs the `claude` CLI on PATH and a Diffbot token where api.resolve_token finds it
(DIFFBOT_TOKEN, DIFFBOT_API_TOKEN, or ~/.diffbot/credentials); the stdio server inherits the environment.
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER_NAME = "diffbot"
PYTHON = pathlib.Path(sys.executable)
CASE_TIMEOUT_SECONDS = 300

# Harness tools the model may use to load a deferred tool schema; never counted as routing.
HARNESS_TOOLS = {"ToolSearch"}


def tool_name(name: str) -> str:
    """mcp__diffbot__search_organizations -> search_organizations"""
    prefix = f"mcp__{SERVER_NAME}__"
    return name[len(prefix):] if name.startswith(prefix) else name


def contains_ci(values: Any, needle: str) -> bool:
    if values is None:
        return False
    if isinstance(values, str):
        values = [values]
    return any(needle.lower() in str(v).lower() for v in values)


@dataclass
class Case:
    name: str
    query: str
    tool: str
    # Each predicate takes the arguments of the FIRST call to `tool` and returns an error string or None.
    args: List[Callable[[dict], Optional[str]]] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    note: str = ""


def expect(key: str, value: Any) -> Callable[[dict], Optional[str]]:
    def check(args: dict) -> Optional[str]:
        got = args.get(key)
        if isinstance(got, (int, float)) and isinstance(value, (int, float)):
            ok = float(got) == float(value)
        else:
            ok = got == value
        return None if ok else f"{key}={got!r}, expected {value!r}"
    return check


def expect_contains(key: str, needle: str) -> Callable[[dict], Optional[str]]:
    def check(args: dict) -> Optional[str]:
        return None if contains_ci(args.get(key), needle) else f"{key}={args.get(key)!r} does not mention {needle!r}"
    return check


CASES: List[Case] = [
    Case(
        name="ma_software_revenue_band",
        query="Find software companies in Massachusetts with revenue between $10 million and $75 million",
        tool="search_organizations",
        args=[
            expect_contains("industry", "software"),
            expect_contains("region", "Massachusetts"),
            expect("min_revenue", 10_000_000),
            expect("max_revenue", 75_000_000),
        ],
        forbidden=["dql", "search_web"],
        note="A bounded revenue band must go through the typed tool, not fall back to raw DQL or web search.",
    ),
]


@dataclass
class Run:
    calls: List[dict]          # {"name", "input", "result", "is_error"} in call order
    final_text: str
    cost_usd: Optional[float]
    duration_ms: Optional[int]
    turns: Optional[int]
    stderr: str


def mcp_config() -> str:
    return json.dumps({
        "mcpServers": {
            SERVER_NAME: {"command": str(PYTHON), "args": [str(ROOT / "diffbot_mcp_server.py")]}
        }
    })


def run_query(query: str, model: Optional[str]) -> Run:
    cmd = [
        "claude", "-p",
        "--output-format", "stream-json", "--verbose",
        "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
        "--mcp-config", mcp_config(),
        "--allowedTools", f"mcp__{SERVER_NAME}__*",
    ]
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, input=query, capture_output=True, text=True, timeout=CASE_TIMEOUT_SECONDS, cwd=ROOT)

    calls: List[dict] = []
    by_id: Dict[str, dict] = {}
    final_text = ""
    cost = duration = turns = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "assistant":
            for block in event["message"]["content"]:
                if block["type"] == "tool_use" and block["name"] not in HARNESS_TOOLS:
                    call = {"name": tool_name(block["name"]), "input": block.get("input") or {}, "result": None, "is_error": None}
                    calls.append(call)
                    by_id[block["id"]] = call
                elif block["type"] == "text":
                    final_text = block["text"]  # the last text block is the answer
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
    return Run(calls, final_text, cost, duration, turns, proc.stderr)


def evaluate(case: Case, run: Run) -> List[str]:
    errors: List[str] = []
    names = [c["name"] for c in run.calls]
    if not run.calls:
        return [f"no MCP tool was called; model said: {run.final_text[:200]!r}"]
    for bad in case.forbidden:
        if bad in names:
            errors.append(f"called forbidden tool {bad}")
    matching = [c for c in run.calls if c["name"] == case.tool]
    if not matching:
        errors.append(f"never called {case.tool}; called {names}")
        return errors
    first = matching[0]
    for predicate in case.args:
        problem = predicate(first["input"])
        if problem:
            errors.append(problem)
    if first["is_error"]:
        errors.append(f"{case.tool} returned an error: {json.dumps(first['result'])[:200]}")
    if not run.final_text.strip():
        errors.append("model produced no final answer")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", help="run only the named case (repeatable)")
    parser.add_argument("--model", help="model alias or id to pass to claude")
    parser.add_argument("--show-calls", action="store_true", help="print every tool call and the final answer")
    options = parser.parse_args()

    if not shutil.which("claude"):
        print("FAIL  the `claude` CLI is not on PATH", file=sys.stderr)
        return 2

    selected = [c for c in CASES if not options.only or c.name in options.only]
    if not selected:
        print(f"no cases match {options.only}; known: {[c.name for c in CASES]}", file=sys.stderr)
        return 2

    failures = 0
    total_cost = 0.0
    for case in selected:
        try:
            run = run_query(case.query, options.model)
        except subprocess.TimeoutExpired:
            failures += 1
            print(f"FAIL  {case.name}  (timed out after {CASE_TIMEOUT_SECONDS}s)")
            continue
        errors = evaluate(case, run)
        total_cost += run.cost_usd or 0.0
        status = "PASS" if not errors else "FAIL"
        failures += bool(errors)
        seconds = (run.duration_ms or 0) / 1000
        print(f"{status}  {case.name}  (tools={[c['name'] for c in run.calls]} turns={run.turns} {seconds:.0f}s ${run.cost_usd or 0:.2f})")
        for error in errors:
            print(f"      - {error}")
        if options.show_calls or errors:
            for call in run.calls:
                print(f"      > {call['name']}({json.dumps(call['input'])})" + ("  [error]" if call["is_error"] else ""))
            if options.show_calls:
                print("      answer:", run.final_text[:500].replace("\n", " "))
        if run.stderr.strip() and errors:
            print("      stderr:", run.stderr.strip()[:500])

    print(f"\n{'PASS' if not failures else 'FAIL'}: {failures} failed of {len(selected)}, ${total_cost:.2f} total")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
