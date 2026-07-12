"""Characterization tests for the chat routing pipeline.

/api/chat and /api/chat/stream share a multi-stage pre-LLM pipeline (fast
command, casual response, operator command, capability route, agentic). These
tests pin the invariant that both endpoints return the SAME reply and source
for deterministic inputs, so the shared-helper refactor stays behavior-
preserving. They use only deterministic commands, so no LLM/network is needed.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.eva.main import app

HEADERS = {"X-Eva-Client": "1"}

# Messages that resolve in the deterministic pre-LLM stages (no provider call):
# one fast-command, one casual response, one capability route.
DETERMINISTIC_MESSAGES = [
    "eva capability truth",
    "pending actions",
    "hello",
    "thanks",
    "what is your architecture",
]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _stream_final(client, message):
    resp = client.post("/api/chat/stream", json={"message": message}, headers=HEADERS)
    assert resp.status_code == 200
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    done = next((e for e in events if e.get("type") == "done"), None)
    meta = next((e for e in events if e.get("type") == "meta"), None)
    return done, meta


@pytest.mark.parametrize("message", DETERMINISTIC_MESSAGES)
def test_chat_and_stream_agree_on_deterministic_reply(client, message):
    plain = client.post("/api/chat", json={"message": message}, headers=HEADERS)
    assert plain.status_code == 200
    body = plain.json()

    done, meta = _stream_final(client, message)
    assert done is not None, "stream produced no done event"
    assert body["reply"] == done["reply"], f"reply diverged between endpoints for {message!r}"
    assert meta is not None and body["source"] == meta["source"], (
        f"source diverged between endpoints for {message!r}: {body['source']} vs {meta.get('source')}"
    )


def test_chat_requires_client_header(client):
    # Lock-in: the CSRF header guard covers the chat endpoints too.
    assert client.post("/api/chat", json={"message": "eva capability truth"}).status_code == 403
    assert client.post("/api/chat/stream", json={"message": "eva capability truth"}).status_code == 403
