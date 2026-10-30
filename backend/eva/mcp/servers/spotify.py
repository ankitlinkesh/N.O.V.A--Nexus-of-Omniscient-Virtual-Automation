"""eva-spotify: NOVA's spotify tools as a stdio MCP server (Phase 160). Run: python -m backend.eva.mcp.servers.spotify"""

from ..domain_server import serve

if __name__ == "__main__":
    serve("spotify")
