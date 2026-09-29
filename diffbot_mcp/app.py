"""The FastMCP instance. Kept in its own module so tool modules can import it without a cycle."""

from fastmcp import FastMCP

from .auth import build_auth

mcp = FastMCP(name="Diffbot MCP Server", auth=build_auth())
