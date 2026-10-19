# Diffbot MCP Server
A Diffbot MCP server with a variety of helpful web knowledge fetching tools for your agent or LLM pipeline.

**What is Diffbot?**
Diffbot is an applied AI lab building models that structure all of human knowledge. Our commercial product suite make it possible to fetch and structure knowledge at the scale of the entire public web.

This is the MCP counterpart to [diffbot-skills](https://github.com/diffbot/diffbot-skills) without requiring bash access.

## Tools

### Web

#### 🧬 extract
**Web fetch tool alternative.** Conventional fetch tools return either 500k+ tokens of HTML or a markdown approximation of the page's content. Extract classifies the page it is fetching and extracts content into a meaningful and consistent JSON schema. Responses are optimized for minimal token usage while maintaining data fidelity. [Learn more.](https://www.diffbot.com/docs/extract/).

#### 🔎 search_web
**Web search tool that ranks accuracy, not popularity.** Built on Diffbot's independent web index. Ranking model heavily favors primary sources over secondary sources (e.g. press release > news piece on said press release). Returns markdown formatted content chunks for source citation, with `num_results` and `max_tokens` controls. [Learn more.](https://www.diffbot.com/docs/web-search/)

Also includes a **page cache reader**. Query `url:<URL>` and it returns Diffbot's already-parsed copy of that page from the index in a fraction of the time for live fetch. Use it for full content from reference prose (docs, articles, papers) and reach for `extract` when the page's current state matters.

#### 🕷️ crawl
**Find all links on a web page (the seed) and extract them all.** A classic web crawl without the need for scraping rules. Crawls run as background jobs and can be polled for status. Crawl automatically classifies and structures pages in a standard ontology for easy querying. Use crawl to archive documentation, take snapshots of web projects, or site mapping. [Learn More.](https://www.diffbot.com/docs/crawl/)

#### 🧠 resolve_entities
**Recognize and resolve entities in text.** Uses Diffbot NLP to recognize organizations, people, places, addresses, and other proper nouns in text. Entities are resolved to entity IDs in the Diffbot Knowledge Graph, and the response includes a ready-made `dql_filter` (`id:or(...)`) to fetch their full records with `dql`. Use to keep AI hallucinations in check and explore deep research opportunities. [Learn more.](https://www.diffbot.com/docs/natural-language/)

### Knowledge Graph

The Diffbot Knowledge Graph contains over 10 billion entities: Organizations, people, news, places, and more, all linked together by their relationship to each other. It is a representation of things, facts, and connections mentioned by the trillions of websites that make up the public web. 

#### 📰 search_news
News and articles by mentioned entity, topic, publisher, language, date range, or sentiment. Newest first by default, relevance-ranked inside a date window. 

#### 🏢 search_organizations
Companies by industry, headquarters, headcount, revenue, funding, ownership, or leadership, plus `similar_to` lookalike lists for competitor mapping.

#### 👤 search_people
People by title, employer, employer industry, skills, education, location, or nationality. Covers people with a public online professional presence only.

#### 🗺️ search_places
Cities, counties, states, countries, and points of interest by name, population, prominence, containing place, or proximity.

#### 💸 search_deals
Funding rounds, investments, and acquisitions by date, size, series, investor, acquirer, or industry.

#### 🎯 dql
**Raw querying of the Diffbot Knowledge Graph.** The general-purpose layer under the five tools above, for any entity type or query shape they do not cover: products, patents, brands, job posts, cross-entity queries, and facet aggregations. Returns compact csv rows with per-type default columns, or full json records on request.

#### 🔬 dql_probe
**Parallel hit counts for several candidate queries.** The way to check that a query is neither too broad nor too narrow before pulling rows, and to compare the `{}` co-constrained form of a query against the loose one.

#### 🧭 dql_ontology
**Helper utility for accurate dql ontology navigation.** Holds the keys to Diffbot's entire ontology and taxonomy reference: entity types, fields, taxonomies, and enums. A guessed field name is silently ignored by the graph, so this is how the exact spelling gets confirmed. Humans don't need to touch this, but feel free to satisfy your curiosity.

## Example Prompts

```
# extract
→ Install Diffbot agent skills following these instructions https://www.diffbot.com/docs/interfaces/agent-skills

# crawl
→ Crawl Philips' websites for product data sheet PDFs

# search_organizations
→ AI companies based in San Francisco started by previous YC founders

# search_deals
→ recent M&As in pharma
```

## Authentication
A free Diffbot token is required for tool use. [Get one here.](https://app.diffbot.com/get-started)

MCP clients that support OAuth (Claude, Cursor, VS Code) can connect to `https://mcp.diffbot.com/mcp` without a token and sign in with a Diffbot account instead.

Otherwise the server looks for a token in this order:

1. `Authorization: Bearer <token>` header or `?token=<token>` query parameter (HTTP transport)
2. `DIFFBOT_TOKEN` or `DIFFBOT_API_TOKEN` environment variable
3. A `DIFFBOT_API_TOKEN=<token>` line in `~/.diffbot/credentials`, the same file the [`db` CLI](https://github.com/diffbot/diffbot-python) and diffbot-skills read, so one credential serves all three

To enable OAuth on a self-hosted HTTP server, set:

| Variable | Example |
| --- | --- |
| `DIFFBOT_OAUTH_ISSUER` | `https://app.diffbot.com` |
| `MCP_BASE_URL` | Public URL of this server, e.g. `https://mcp.diffbot.com` |
| `DIFFBOT_OAUTH_CLIENT_ID` / `DIFFBOT_OAUTH_CLIENT_SECRET` | Confidential client allowed to call the dashboard's introspection endpoint |

OAuth is off when `DIFFBOT_OAUTH_ISSUER` is unset. With `docker compose`, put these in `/etc/diffbot-mcp.env` on the host; the server runs without the file.

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

The code lives in `diffbot_mcp/`: `api.py` (token resolution and the shared request helper), `dql.py` (query execution, default columns, the cached ontology), `dql_builder.py` (pure DQL assembly), and one module per tool under `tools/`. `diffbot_mcp_server.py` is the entry point.

## Help & Support
This project is built and maintained by [@jeromechoo](https://github.com/jeromechoo). For support, file an issue and he'll get back to you as soon as he can. For faster answers, write to [sales@diffbot.com](mailto:sales@diffbot.com) 😜.
