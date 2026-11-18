# Installing Diffbot MCP (instructions for AI agents)

Diffbot MCP gives you web search, page extraction, site crawls, and Diffbot Knowledge Graph queries.
Pick one of the two options below. Never write a real token into a file that is committed to git.

## Option 1: hosted server (no token to paste)

Add a remote Streamable HTTP server. The user signs in with a Diffbot account (OAuth) the first time a tool runs.

```json
{
  "mcpServers": {
    "diffbot-mcp": {
      "type": "streamable-http",
      "url": "https://mcp.diffbot.com/mcp"
    }
  }
}
```

If your client cannot do OAuth, send the header `Authorization: Bearer <YOUR_DIFFBOT_TOKEN>` instead.

## Option 2: local server with `uvx`

Requires [uv](https://docs.astral.sh/uv/). The server reads its token from `DIFFBOT_TOKEN`,
`DIFFBOT_API_TOKEN`, or `~/.diffbot/credentials`.

```json
{
  "mcpServers": {
    "diffbot-mcp": {
      "command": "uvx",
      "args": ["diffbot-mcp"],
      "env": { "DIFFBOT_TOKEN": "<YOUR_DIFFBOT_TOKEN>" }
    }
  }
}
```

A free token is available at https://app.diffbot.com/get-started. Ask the user for it; do not invent one.

## Check that it works

List the server's tools. You should see 12: `extract`, `search_web`, `crawl`, `resolve_entities`,
`search_news`, `search_organizations`, `search_people`, `search_places`, `search_deals`, `dql`,
`dql_probe`, and `dql_ontology`. Then try `search_web` with a short query.

## Links

- Docs: https://www.diffbot.com/docs/interfaces/mcp-server
- Source: https://github.com/diffbot/diffbot-mcp
- Support: support@diffbot.com
