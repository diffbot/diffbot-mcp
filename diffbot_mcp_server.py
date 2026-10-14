import os

from diffbot_mcp.server import mcp

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    mcp.run(transport)
