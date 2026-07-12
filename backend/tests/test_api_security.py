"""Executable spec for the HTTP tool-call surface in backend/eva/api/routes.py.

Current state (backend/eva/api/routes.py):

    tools = ToolRegistry()

    @router.post("/tools/{tool_name}")
    async def run_tool(tool_name: str, body: dict | None = None) -> dict:
        try:
            result = tools.run(tool_name, **(body or {}))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"tool": tool_name, "result": result}

This endpoint calls ToolRegistry.run() directly with no header/auth check of
any kind, so it inherits (and today, bypasses) all the same gating gaps as
test_registry_gate.py. It also has no client-identity header requirement at
all -- any local process that can reach the port can call any tool.

Target design: a required `X-Eva-Client` header for state-changing/tool
calls (enforced by middleware still to be written), and gated tool calls
returning requires_confirmation instead of executing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.eva.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_file_delete_via_api_does_not_bypass_confirmation(client, sandbox_dir):
    target = sandbox_dir / "api_victim.txt"
    target.write_text("keep me", encoding="utf-8")

    response = client.post(
        "/api/tools/file.delete",
        json={"path": str(target), "confirmed": True},
        headers={"X-Eva-Client": "1"},
    )

    assert response.status_code == 200
    body = response.json()
    result = body.get("result") or {}
    assert result.get("requires_confirmation") is True, f"unexpected API response: {body}"
    assert target.exists(), "POST /api/tools/file.delete deleted the file without ledger confirmation"


def test_tool_call_without_client_header_is_rejected(client):
    response = client.post("/api/tools/workspace_status", json={}, headers={})

    assert response.status_code == 403, (
        f"expected 403 for a tool call missing X-Eva-Client, got {response.status_code}: {response.text}"
    )


def test_health_get_without_client_header_still_works(client):
    """Lock-in: GETs (read-only, no side effects) are not blocked by the
    client-header middleware, even without X-Eva-Client."""
    response = client.get("/api/health")

    assert response.status_code == 200
