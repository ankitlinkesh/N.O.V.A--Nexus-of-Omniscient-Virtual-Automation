"""eva-news: NOVA's read-only information tools (headlines, weather) as a stdio MCP server (Phase 160). Run: python -m backend.eva.mcp.servers.news"""

from ..domain_server import serve

if __name__ == "__main__":
    serve("news")
