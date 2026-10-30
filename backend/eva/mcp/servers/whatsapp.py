"""eva-whatsapp: NOVA's whatsapp tools as a stdio MCP server (Phase 160). Run: python -m backend.eva.mcp.servers.whatsapp"""

from ..domain_server import serve

if __name__ == "__main__":
    serve("whatsapp")
