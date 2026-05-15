"""
Unit tests for outbound event publisher (v3 §4.3).

Strategy: use a stub EventBus that either returns a fake msg id ("stream"
path) or returns None ("REST fallback" path). REST is short-circuited via
monkeypatching httpx.AsyncClient.post to a fake.
"""
import json
from typing import Any, Optional

import httpx
import pytest

from core.event_bus import EventBus
from services.events.publisher import emit_audit_action, emit_usage_metric

pytestmark = pytest.mark.unit


class _StubBus(EventBus):
    """An EventBus that records calls and replays a scripted response."""

    def __init__(self, publish_result: Optional[str] = "stream-1"):
        super().__init__(url="redis://stub")
        self.published: list[tuple[str, dict[str, Any]]] = []
        self._publish_result = publish_result

    async def publish(self, stream, event):  # type: ignore[override]
        self.published.append((stream, event))
        return self._publish_result


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeHttpClient:
    """httpx.AsyncClient stand-in. Records the last POST and returns a scripted status."""

    last: dict[str, Any] = {}

    def __init__(self, *, status_code: int = 200, raise_on_post: bool = False):
        self._status_code = status_code
        self._raise = raise_on_post

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, url, json=None, headers=None):
        _FakeHttpClient.last = {"url": url, "json": json, "headers": headers}
        if self._raise:
            raise httpx.ConnectError("simulated")
        return _FakeResponse(self._status_code)


# ── usage.metric ────────────────────────────────────────────────────────────


async def test_usage_metric_uses_stream_when_redis_ok():
    bus = _StubBus(publish_result="stream-msg-1")
    result = await emit_usage_metric(
        tenant_id="t1", metric="proposals_generated", value=1, bus=bus
    )
    assert result == "stream"
    assert len(bus.published) == 1
    stream, event = bus.published[0]
    assert stream.endswith(".events")
    assert event["type"] == "usage.metric"
    assert event["tenant_id"] == "t1"
    assert event["value"] == 1


async def test_usage_metric_falls_back_to_rest_when_stream_fails(monkeypatch):
    bus = _StubBus(publish_result=None)  # simulate Redis down
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeHttpClient(status_code=200))

    result = await emit_usage_metric(tenant_id="t1", metric="x", value=1, bus=bus)
    assert result == "rest"
    assert "/usage/events" in _FakeHttpClient.last["url"]
    assert _FakeHttpClient.last["json"]["tenant_id"] == "t1"


async def test_usage_metric_dropped_when_both_fail(monkeypatch):
    bus = _StubBus(publish_result=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeHttpClient(raise_on_post=True))
    result = await emit_usage_metric(tenant_id="t1", metric="x", value=1, bus=bus)
    assert result == "dropped"


async def test_usage_metric_dropped_on_4xx(monkeypatch):
    bus = _StubBus(publish_result=None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeHttpClient(status_code=400))
    result = await emit_usage_metric(tenant_id="t1", metric="x", value=1, bus=bus)
    assert result == "dropped"


# ── audit.action ────────────────────────────────────────────────────────────


async def test_audit_action_carries_all_optional_fields():
    bus = _StubBus()
    await emit_audit_action(
        tenant_id="t1",
        user_id="u1",
        action="proposal.created",
        entity="Proposal",
        entity_id="p1",
        changes={"field": "value"},
        ip_address="10.0.0.1",
        trace_id="trace-abc",
        bus=bus,
    )
    event = bus.published[0][1]
    assert event["type"] == "audit.action"
    assert event["user_id"] == "u1"
    assert event["action"] == "proposal.created"
    assert event["entity"] == "Proposal"
    assert event["entity_id"] == "p1"
    assert event["changes"] == {"field": "value"}
    assert event["ip_address"] == "10.0.0.1"
    assert event["trace_id"] == "trace-abc"


# ── prefer-REST escape hatch (B4 fallback) ─────────────────────────────────


async def test_prefer_rest_skips_stream(monkeypatch):
    from core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "EVENT_PUBLISHER_PREFER_REST", True)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeHttpClient(status_code=200))

    bus = _StubBus(publish_result="should-not-be-called")
    result = await emit_usage_metric(tenant_id="t1", metric="x", value=1, bus=bus)
    assert result == "rest"
    assert bus.published == []  # stream skipped entirely
