"""Tiny in-repo FastMCP stdio server used for live testing of the MCP client
subsystem. Not started automatically by anything -- run it explicitly, or let
the MCP client spawn it as a subprocess per the example config entry
(config/mcp_servers.example.json, disabled by default)."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("eva-example")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the given text back."""
    return f"echo: {text}"


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run()
