"""
Unit tests for services.events.audit.audit().

Stubs the publisher and a Request to verify trace_id / IP / user_id flow.
"""
from types import SimpleNamespace
from typing import Any

import pytest

from services.events import audit as audit_mod

pytestmark = pytest.mark.unit


class _FakeRequest:
    def __init__(self, *, trace_id: str | None = None, client_host: str = "1.2.3.4",
                 forwarded: str | None = None):
        self.state = SimpleNamespace(trace_id=trace_id) if trace_id else SimpleNamespace()
        self.client = SimpleNamespace(host=client_host) if client_host else None
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


@pytest.fixture
def captured(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def fake_emit(**kwargs):
        calls.append(kwargs)
        return "stream"

    monkeypatch.setattr(audit_mod, "emit_audit_action", fake_emit)
    return calls


async def test_audit_extracts_trace_id_from_request_state(captured, sap_world):
    req = _FakeRequest(trace_id="trace-xyz")
    user = sap_world["owner"]

    result = await audit_mod.audit(
        req, user,
        action="proposal.created",
        entity="Proposal",
        entity_id="p-1",
        changes={"title": "Test"},
    )

    assert result == "stream"
    assert len(captured) == 1
    call = captured[0]
    assert call["tenant_id"] == user.tenant_id
    assert call["user_id"] == user.id
    assert call["action"] == "proposal.created"
    assert call["entity_id"] == "p-1"
    assert call["trace_id"] == "trace-xyz"
    assert call["ip_address"] == "1.2.3.4"
    assert call["changes"] == {"title": "Test"}


async def test_audit_prefers_xff_over_client_host(captured, sap_world):
    req = _FakeRequest(client_host="1.2.3.4", forwarded="10.0.0.9, 1.2.3.4")
    await audit_mod.audit(req, sap_world["owner"], action="x", entity="X")
    assert captured[0]["ip_address"] == "10.0.0.9"


async def test_audit_falls_back_to_header_trace_id(captured, sap_world):
    # No request.state.trace_id, but header is set.
    req = _FakeRequest()
    req.headers = {"X-Trace-ID": "from-header"}
    await audit_mod.audit(req, sap_world["owner"], action="x", entity="X")
    assert captured[0]["trace_id"] == "from-header"


async def test_audit_publisher_failure_is_swallowed(monkeypatch, sap_world):
    async def boom(**kwargs):
        raise RuntimeError("publisher down")

    monkeypatch.setattr(audit_mod, "emit_audit_action", boom)
    req = _FakeRequest(trace_id="x")
    # Must not raise — audit is fire-and-forget.
    result = await audit_mod.audit(req, sap_world["owner"], action="x", entity="X")
    assert result == "dropped"


async def test_audit_without_request_still_works(captured, sap_world):
    await audit_mod.audit(None, sap_world["owner"], action="x", entity="X", entity_id="e1")
    assert captured[0]["trace_id"] is None
    assert captured[0]["ip_address"] is None
    assert captured[0]["entity_id"] == "e1"
