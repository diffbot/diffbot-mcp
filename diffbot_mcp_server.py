import os

from diffbot_mcp.server import mcp


def main() -> None:
    mcp.run(os.getenv("MCP_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
