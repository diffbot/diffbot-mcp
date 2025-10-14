# Diffbot MCP Server
A Diffbot MCP server with a variety of helpful web data handling tools for your agent or LLM pipeline.

**What is Diffbot?**
Diffbot is a small research company building AI that structure the web. Our products connect apps to the structured web automatically, like an API for all of the public web.

## Tools

#### 🧬 extract
**Web fetch tool alternative.** Conventional fetch tools return either 500k+ tokens of HTML or a markdown approximation of the page's content. Extract classifies the page it is fetching and extracts content into a meaningful and consistent JSON structure. Responses are optimized for minimal token usage while maintaining data fidelity. Powered by [Diffbot Extract API](https://docs.diffbot.com/docs/getting-started-with-diffbot-extract).

#### 🔎 search_web
**Web search tool that ranks accuracy, not popularity.** Built on Diffbot's first party web index. Ranking model heavily favors primary sources over secondary sources (e.g. press release > news piece on said press release). Returns markdown formatted content chunks for source citation. Optimized token management built-in. 

#### 🪄 enhance
**Web lookup tool for organizations and people.** Unlike web search, `enhance` will return structured data from the Diffbot Knowledge Graph on an organization or person (by name, url, or other acceptable input). Helpful for verifying facts, market research, or sales intelligence workflows.

## Authentication
A free Diffbot token is required for tool use. [Get one here.](https://app.diffbot.com/get-started)

## Get Started

The easiest way to get started is to connect your MCP client directly to the remote MCP server hosted by Diffbot. 

```
https://mcp.diffbot.com/mcp/?token=<YOUR_DIFFBOT_TOKEN>
```

This repo deploys directly to the remote server.

### Installation (Local)

Clone the repository
```bash
git clone git@github.com:diffbot/diffbot-mcp.git
```

Install requirements
```bash
pip install .
```

You can now run the server with `python3 diffbot_mcp_server.py`, or skip this step if you will be setting this server up with an MCP client.

### Installation (Docker)

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