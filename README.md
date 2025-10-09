# Diffbot MCP Server
A Diffbot MCP server with a variety of helpful web data handling tools for your agent or LLM pipeline.

**What is Diffbot?**
Diffbot is a small research company building AI that structure the web. Our products connect apps to the structured web automatically, like an API for all of the public web.

## Tools

#### 🧬 extract
Alternative to a generic web fetch tool. Conventional markdown extraction libraries handle images and other contextually structured content poorly. Extract uses [Diffbot Extract API](https://docs.diffbot.com/docs/getting-started-with-diffbot-extract) to return a markdown extraction and structured data from a URL. Diffbot Extract responses are optimized for minimal token usage while maintaining maximum data fidelity.

#### 🔎 search_web
Web search built on Diffbot's first party web index. Ranking heavily prioritizes primary sources over secondary sources (no more rabbit holing into inline article links). Returns markdown formatted content chunks for source citation. Optimized token management built-in. 

#### 🪄 enhance
Web lookup tool for organizations and people. Unlike web search, `enhance` will return structured data from the Diffbot Knowledge Graph on an organization or person (by name, url, or other acceptable input) for factual verification or market research use cases.

## Authentication
A free Diffbot token is required for tool use. [Get one here.](https://app.diffbot.com/get-started)

## Get Started
To setup locally on Claude Desktop, follow the [official installation guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers) and use this example  `claude_desktop_config.json` configuration (replace variables as needed).

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
                "DIFFBOT_TOKEN": "<YOUR DIFFBOT TOKEN>"
            }
        }
    }
}
```
<details>
<summary>Visual Studio Code / Copilot</summary>

To setup in VS Code, try this modified config for better secrets management.

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

## Help & Support
This project is built and maintained by [@jeromechoo](https://github.com/jeromechoo). For support, file an issue and he'll get back to you as soon as he can. For faster answers, write to [sales@diffbot.com](mailto:sales@diffbot.com) 😜. 