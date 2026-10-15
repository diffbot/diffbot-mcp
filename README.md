# Diffbot MCP Server
A Diffbot MCP server with a variety of helpful web data handling tools for your agent or LLM pipeline.

**What is Diffbot?**
Diffbot is a small research company building AI that structure the web. Our products connect apps to the structured web automatically, like an API for all of the public web.

This server is the MCP counterpart of [diffbot-skills](https://github.com/diffbot/diffbot-skills): the same capabilities, with nothing to install on the client.

## Tools

### Web

#### 🧬 extract
**Web fetch tool alternative.** Conventional fetch tools return either 500k+ tokens of HTML or a markdown approximation of the page's content. Extract classifies the page it is fetching and extracts content into a meaningful and consistent JSON structure. Responses are optimized for minimal token usage while maintaining data fidelity. Powered by [Diffbot Extract API](https://docs.diffbot.com/docs/getting-started-with-diffbot-extract).

#### 🔎 search_web
**Web search tool that ranks accuracy, not popularity.** Built on Diffbot's first party web index. Ranking model heavily favors primary sources over secondary sources (e.g. press release > news piece on said press release). Returns markdown formatted content chunks for source citation, with `num_results` and `max_tokens` controls.

Also a **URL reader**: query `url:<URL> <what you need>` and it returns Diffbot's already-parsed copy of that page from the index in about 300ms, one record on a hit and zero on a miss, even for pages that block live fetchers. Use it for reference prose (docs, articles, papers) and reach for `extract` when the page's current state matters or the whole document is needed.

#### 🕷️ crawl
**Find all links on a web page (the seed) and extract them all.** A classic web crawl, with an ontological web extraction bonus. Crawls run as background jobs: `start`, poll `status`, inspect per-URL outcomes with `urls`, page through `results`, `list` and `delete`. Use crawl to archive documentation, take snapshots of web projects, or site mapping.

#### 🧠 resolve_entities
**Recognize and resolve entities in text.** Uses Diffbot NLP to recognize organizations, people, places, addresses, and other proper nouns in text. Entities are resolved to entity IDs in the Diffbot Knowledge Graph, and the response includes a ready-made `dql_filter` (`id:or(...)`) to fetch their full records with `dql`. Keeps hallucinations in check and gives AI the context it needs to navigate deep research.

### Knowledge Graph

The Diffbot Knowledge Graph is a Wikipedian-scale linked database of organizations, people, articles, places, products, and deals. Five typed tools cover the questions people actually ask; each builds the query for you, bakes in the defaults that were verified against the live graph, and returns the DQL it ran so it can be refined by hand.

#### 📰 search_news
News and articles by mentioned entity, topic, publisher, language, date range, or sentiment. Newest first by default, relevance-ranked inside a date window. Topics are resolved against the ArticleCategory taxonomy.

#### 🏢 search_organizations
Companies by industry, headquarters, headcount, revenue, funding, ownership, or leadership, plus `similar_to` lookalike lists for competitor mapping. Industry is resolved against the OrganizationCategory taxonomy; location means headquarters unless `any_office` is set.

#### 👤 search_people
People by title, employer, employer industry, skills, education, location, or nationality. Employment conditions are co-constrained on one job (the loose form inflates counts about 9x), C-suite titles are expanded to both spellings, and the rendered Title and Employer are the job that matched. `leadership_of` answers "who runs X" from the curated Organization fields. Covers people with a public online professional presence only.

#### 🗺️ search_places
Cities, counties, states, countries, and points of interest by name, population, prominence, containing place, or proximity. Accented names are searched in both spellings.

#### 💸 search_deals
Funding rounds, investments, and acquisitions by date, size, series, investor, acquirer, or industry. Acquisitions are read from the acquired company (standalone Acquisition records are stubs), and an industry filter is applied on the company side because a deal's investee carries no categories.

#### 🎯 dql
**Queries the Diffbot Knowledge Graph directly.** The general-purpose layer under the five tools above, for any entity type or query shape they do not cover: products, patents, brands, job posts, cross-entity queries, and facet aggregations. Returns compact csv rows with per-type default columns, or full json records on request.

#### 📤 export_csv
**Writes a result set to a CSV file.** Takes the DQL any search tool returns, with optional columns, and writes the whole result set (not a page) where the server runs; without a path it returns the CSV text. Dates and large numbers are cleaned on the way out.

#### 🔬 dql_probe
**Parallel hit counts for several candidate queries.** The way to check that a query is neither too broad nor too narrow before pulling rows, and to compare the `{}` co-constrained form of a query against the loose one.

#### 🧭 dql_ontology
**Helper utility for accurate dql ontology navigation.** Holds the keys to Diffbot's entire ontology and taxonomy reference: entity types, fields, taxonomies, and enums. A guessed field name is silently ignored by the graph, so this is how the exact spelling gets confirmed. Humans don't need to touch this, but feel free to satisfy your curiosity.

## Prompts

Ten prompts carry the long-form workflow guidance from diffbot-skills: the operator reference, the measured traps, the display rules. In Claude Code they surface as slash commands (`/mcp__diffbot-mcp__news`, `/mcp__diffbot-mcp__dql`, ...); in Claude Desktop they are listed under the server's prompts. Each takes an optional `request` argument.

| Prompt | Covers |
| --- | --- |
| `news` | The sort rule, narrowing levers, entity-specific sentiment, coverage facets |
| `organizations` | Industry taxonomy, HQ vs offices, `strict:` name matching, `near`, `similarTo`, subqueries |
| `people` | The `{}` co-constraint rule, employer-industry filtering, C-suite and board title traps, coverage boundary |
| `places` | The place-type hierarchy, containment, the continent gap, diacritics |
| `deals` | Investment vs Organization vs Transaction routing, the investee industry gap, amount and currency handling |
| `dql` | Full DQL operator reference, ontology lookup, probing, csv vs json fetches |
| `web-search` | The index-before-fetch rule and when a cached copy cannot be trusted |
| `extract` | When a live fetch is actually needed, page types, response fields |
| `entities` | Confidence vs salience, bridging text to DQL with entity ids |
| `crawl` | Start, poll, inspect, read |

## Authentication
A free Diffbot token is required for tool use. [Get one here.](https://app.diffbot.com/get-started)

The server looks for a token in this order:

1. `Authorization: Bearer <token>` header or `?token=<token>` query parameter (HTTP transport)
2. `DIFFBOT_TOKEN` or `DIFFBOT_API_TOKEN` environment variable
3. A `DIFFBOT_API_TOKEN=<token>` line in `~/.diffbot/credentials`, the same file the [`db` CLI](https://github.com/diffbot/diffbot-python) and diffbot-skills read, so one credential serves all three

## Get Started

### Quick Start

The easiest way to get started is to connect your MCP client directly to the remote MCP server hosted by Diffbot.

```
https://mcp.diffbot.com/mcp?token=<YOUR_DIFFBOT_TOKEN>
```

This repo deploys directly to the remote server.

### Local Installation

Clone the repository
```bash
git clone git@github.com:diffbot/diffbot-mcp.git
```

Install requirements
```bash
pip install .
```

You can now run the server with `python3 diffbot_mcp_server.py`, or skip this step if you will be setting this server up with an MCP client.

#### (Optional) Docker Install

Build the image
```bash
docker build -t diffbot-mcp .
```

### Setup with MCP Clients

To setup Claude Desktop, follow the [official installation guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers) and use this example  `claude_desktop_config.json` configuration (replace variables as needed).

This standard config works with most IDEs and environments.

```json
{
    "mcpServers": {
        "diffbot-mcp": {
            "command": "python3",
            "args": [
                "/<YOUR_PROJECT_FOLDER>/diffbot-mcp/diffbot_mcp_server.py"
            ],
            "env": {
                "DIFFBOT_TOKEN": "<YOUR_DIFFBOT_TOKEN>"
            }
        }
    }
}
```
For Docker installs, follow this configuration.

```json
{
    "mcpServers": {
        "diffbot-mcp": {
            "command": "docker",
            "args": [
                "run",
                "--rm",
                "-i",
                "-e", "DIFFBOT_TOKEN=<YOUR_DIFFBOT_TOKEN>",
                "diffbot-mcp"
            ]
        }
    }
}
```

<details>
<summary>Visual Studio Code / Copilot</summary>

For remote setup, simply enter the remote server URL and include "http" as the transport type.

```json
{
  "servers": {
    "diffbot-mcp": {
      "type": "http",
      "url": "https://mcp.diffbot.com/mcp/?token=<YOUR_DIFFBOT_TOKEN>"
    }
  }
}
```

For local setup, try this modified config for better secrets management.

```json
{
	"servers": {
        "diffbot-mcp": {
            "command": "python3",
            "args": [
                "/<YOUR_PROJECT_FOLDER>/diffbot-mcp/diffbot_mcp_server.py"
            ],
            "env": {
                "DIFFBOT_TOKEN": "${input:diffbot-api-key}"
            }
        }
	},
	"inputs": [
		{
			"password": true,
			"id": "diffbot-api-key",
			"type": "promptString",
			"description": "Diffbot API Key"
		}
	]
}
```
</details>

## Development

```bash
python3 -m venv env && env/bin/pip install -e '.[dev]'
env/bin/python -m pytest tests/test_builder.py     # generated-DQL assertions, no network
env/bin/python tests/smoke.py                      # one live call per tool, needs a token
env/bin/python tests/eval_routing.py               # real questions through `claude -p`, asserts tool routing; costs model tokens
MCP_TRANSPORT=http env/bin/python diffbot_mcp_server.py & ./test.sh   # HTTP transport smoke
```

The code lives in `diffbot_mcp/`: `api.py` (token resolution and the shared request helper), `dql.py` (query execution, default columns, the cached ontology), `dql_builder.py` (pure DQL assembly), one module per tool under `tools/`, and the prompt bodies under `prompts/`. `diffbot_mcp_server.py` is the entry point.

## Help & Support
This project is built and maintained by [@jeromechoo](https://github.com/jeromechoo). For support, file an issue and he'll get back to you as soon as he can. For faster answers, write to [sales@diffbot.com](mailto:sales@diffbot.com) 😜.
