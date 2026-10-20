"""The FastMCP instance. Kept in its own module so tool modules can import it without a cycle."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .auth import build_auth

mcp = FastMCP(name="Diffbot MCP Server", auth=build_auth())

# Every tool except crawl only reads from Diffbot's APIs or the open web
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
