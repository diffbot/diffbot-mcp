"""End-to-end smoke test against the live Diffbot APIs, driven through an in-process MCP client.

Run with a token available to api.resolve_token (DIFFBOT_TOKEN, DIFFBOT_API_TOKEN, or
~/.diffbot/credentials):

    env/bin/python tests/smoke.py

Runs every check and exits non-zero if any failed. Prints the serialized tools/list size
so the always-on schema cost is a number.
"""

import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastmcp import Client  # noqa: E402

from diffbot_mcp.server import mcp  # noqa: E402

EXPECTED_TOOLS = {
    "extract", "search_web", "resolve_entities", "crawl", "dql", "dql_probe", "dql_ontology",
    "search_news", "search_organizations", "search_people", "search_places", "search_deals",
}
EXPECTED_PROMPTS = {"news", "organizations", "people", "places", "deals", "dql", "web-search", "extract", "entities", "crawl"}

failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    status = "PASS" if condition else "FAIL"
    if not condition:
        failures += 1
    print(f"{status}  {label}" + (f"  ({detail})" if detail else ""))


async def call(client: Client, tool: str, **arguments) -> dict:
    result = await client.call_tool(tool, arguments, raise_on_error=False)
    if result.is_error:
        text = result.content[0].text if result.content else ""
        raise RuntimeError(f"{tool} returned an error: {text}")
    return result.data if result.data is not None else json.loads(result.content[0].text)


async def main() -> int:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        prompts = await client.list_prompts()
        names = {t.name for t in tools}
        check("tools/list has exactly the expected tools", names == EXPECTED_TOOLS, f"missing={EXPECTED_TOOLS - names} extra={names - EXPECTED_TOOLS}")
        check("enhance is gone", "enhance" not in names)
        check("prompts/list has the ten prompts", {p.name for p in prompts} == EXPECTED_PROMPTS)
        payload = json.dumps([t.model_dump(mode="json") for t in tools])
        print(f"INFO  tools/list serialized size: {len(payload)} bytes")

        prompt = await client.get_prompt("news", {"request": "latest Nvidia news"})
        text = prompt.messages[0].content.text
        check("news prompt renders with the request appended", text.startswith("# Diffbot News Search") and text.endswith("User request: latest Nvidia news"))

        r = await call(client, "search_web", query="diffbot", num_results=1)
        check("search_web honors num_results", len(r.get("search_results", [])) == 1, f"got {len(r.get('search_results', []))}")
        check("search_web reports timeMs", "timeMs" in r)

        r = await call(client, "search_web", query="url:https://en.wikipedia.org/wiki/Diffbot knowledge graph")
        check("search_web url: lookup returns one record", len(r.get("search_results", [])) == 1)

        r = await call(client, "extract", url="diffbot.com")
        check("extract normalizes a scheme-less URL and returns objects", bool(r.get("objects")), f"keys={list(r)[:5]}")

        r = await call(client, "resolve_entities", text="Apple CEO Tim Cook announced record quarterly earnings.")
        check("resolve_entities returns entities and a dql_filter", bool(r.get("entities")) and (r.get("dql_filter") or "").startswith("id:or("), str(r.get("dql_filter")))

        r = await call(client, "dql", query=f"type:Organization {r['dql_filter']}", size=5)
        check("dql accepts the dql_filter and returns rows", r.get("returned", 0) >= 1, f"hits={r.get('hits')}")

        r = await call(client, "dql_probe", queries=[
            'type:Person employments.{title:"Chief Executive Officer" isCurrent:true employer.categories.name:"Semiconductor Companies"}',
            'type:Person employments.{title:"Chief Executive Officer" isCurrent:true} employments.employer.categories.name:"Semiconductor Companies"',
            'type:Organization similarTo(name:"OpenAI")',
        ])
        rows = r["results"]
        check("dql_probe: loose employment form inflates the count", (rows[1]["hits"] or 0) > (rows[0]["hits"] or 0), f"{rows[0]['hits']} vs {rows[1]['hits']}")
        check("dql_probe: similarTo reports an error instead of 0", rows[2].get("error") is not None)

        r = await call(client, "dql_ontology", action="taxonomy", name="OrganizationCategory", search="semiconductor")
        check("dql_ontology finds Semiconductor Companies", "Semiconductor Companies" in r.get("results", []))

        r = await call(client, "dql", query='type:Organization strict:name:"Tesla" get:name,ceo,founders', size=1, format="json")
        check("dql json format returns entity records with get: fields", bool(r.get("results")) and "ceo" in r["results"][0], str(list(r["results"][0].keys())[:8]) if r.get("results") else "")

        r = await call(client, "search_news", mentions=["Nvidia"], size=3)
        check("search_news returns dated rows newest first", r.get("returned") == 3 and r["dql"].endswith("sortBy:date") and all("Date" in row for row in r["results"]), r.get("dql"))
        check("search_news dates are stripped of the d prefix", all(not row["Date"].startswith("d") for row in r["results"]))

        r = await call(client, "search_news", topic="artificial intelligence", since="2026-08-01", size=2)
        check("search_news resolves a topic and drops the sort inside a date window", r.get("dql", "") == 'type:Article categories.name:"Artificial Intelligence" date>="2026-08-01"', r.get("dql"))

        r = await call(client, "search_organizations", industry=["semiconductor companies"], country="United States", is_public=True, size=3)
        check("search_organizations resolves the industry case-insensitively", r.get("dql", "").startswith('type:Organization categories.name:"Semiconductor Companies"'), r.get("dql"))
        check("search_organizations returns rows with a hit count", r.get("returned") == 3 and (r.get("hits") or 0) > 100, f"hits={r.get('hits')}")

        r = await call(client, "search_organizations", industry=["software"], size=1)
        check("search_organizations returns candidates for an ambiguous industry", r.get("dql") is None and len(r.get("candidates", {}).get("industry", [])) > 1)

        r = await call(client, "search_organizations", similar_to="OpenAI", country="United States", size=3)
        check("search_organizations similar_to returns a ranked list with hits null", r.get("returned") == 3 and r.get("hits") is None)

        r = await call(client, "search_people", leadership_of="tesla.com")
        check("search_people leadership_of reads ceo and founders", r.get("ceo") == "Elon Musk" and "Martin Eberhard" in r.get("founders", []), f"ceo={r.get('ceo')} founders={r.get('founders')}")

        r = await call(client, "search_people", employer="Nvidia", title=["CEO"], size=3)
        check("search_people renders the matched employer", r.get("returned", 0) >= 1 and all("Nvidia" in (row.get("Employer") or "") for row in r["results"]), str(r.get("results"))[:200])
        check("search_people expands the CEO title", 'title:or("Chief Executive Officer","CEO")' in r.get("dql", ""), r.get("dql"))

        r = await call(client, "search_places", kind="city", country="Japan", min_population=1000000, sort="population", size=3)
        check("search_places returns populated cities largest first", r.get("returned") == 3 and int(r["results"][0].get("Population", 0)) >= int(r["results"][-1].get("Population", 0)), str(r.get("results"))[:200])

        r = await call(client, "search_places", kind="city", name="Kópavogur", size=2)
        check("search_places finds the accented name via both spellings", (r.get("hits") or 0) >= 1, r.get("dql"))

        r = await call(client, "search_deals", investor="Sequoia Capital", size=3)
        check("search_deals returns funding rows with amounts and dates", r.get("returned") == 3 and any("Amount" in row for row in r["results"]), str(r.get("results"))[:200])

        r = await call(client, "search_deals", kind="acquisitions", acquirer="Microsoft", sort="largest", size=3)
        check("search_deals acquisitions route through acquiredBy", r.get("dql", "").startswith("type:Organization isAcquired:true") and r.get("returned") == 3, r.get("dql"))

        r = await call(client, "search_deals", industry="Artificial Intelligence Software", min_amount=50000000, since="2026-01-01", size=3)
        check("search_deals industry filter lists matching rounds per company", r.get("returned", 0) >= 1 and all(row.get("Amount", 0) >= 50000000 for row in r["results"]), str(r.get("results"))[:200])

        r = await call(client, "search_deals", since="2026-01-01", facet="series", size=5)
        check("search_deals facet returns buckets", r.get("facet") is True and len(r.get("results", [])) == 5)

        r = await call(client, "crawl", action="list")
        check("crawl list returns job summaries", isinstance(r.get("jobs"), list))

    print(f"\n{'FAIL' if failures else 'PASS'}: {failures} failed check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
