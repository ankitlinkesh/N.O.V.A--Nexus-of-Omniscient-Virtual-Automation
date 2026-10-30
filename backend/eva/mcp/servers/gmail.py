"""eva-gmail: NOVA's gmail tools as a stdio MCP server (Phase 160). Run: python -m backend.eva.mcp.servers.gmail"""

from ..domain_server import serve

if __name__ == "__main__":
    serve("gmail")
