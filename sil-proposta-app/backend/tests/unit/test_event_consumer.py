"""
End-to-end consumer test against fakeredis:

  1. Publish two events to portal.events (XADD)
  2. Run one batch of the consumer
  3. Assert handlers fired (state changed) and messages were ACKed
     (pending list empty)
"""
import fakeredis.aioredis as fakeredis_async
import pytest

from core.event_bus import (
    CONSUMER_GROUP,
    PORTAL_EVENTS_STREAM,
    EventBus,
    _flatten,
)
from services.events.consumer import _process_batch

pytestmark = pytest.mark.unit


class _FakeBus(EventBus):
    """EventBus wired against fakeredis instead of a real connection."""

    def __init__(self):
        super().__init__(url="redis://fake")
        self._client = fakeredis_async.FakeRedis(decode_responses=True)


async def test_consumer_dispatches_and_acks(db, sap_world):
    bus = _FakeBus()
    client = await bus.client()
    tid = sap_world["tenant"].id

    # Seed two events.
    await client.xadd(PORTAL_EVENTS_STREAM, _flatten({"type": "tenant.suspended", "tenant_id": tid, "reason": "test"}))
    await client.xadd(PORTAL_EVENTS_STREAM, _flatten({"type": "subscription.upgraded", "tenant_id": tid, "plan_slug": "pro", "max_users": 50}))

    await bus.ensure_consumer_group(PORTAL_EVENTS_STREAM, CONSUMER_GROUP)

    # Override async_session inside the consumer so it sees the test DB.
    import services.events.consumer as consumer_mod
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session_cm():
        yield db

    consumer_mod.async_session = _session_cm
    try:
        processed = await _process_batch(bus, "test-1", count=10, block_ms=100)
    finally:
        # Restore real factory for other tests.
        from core.database import async_session
        consumer_mod.async_session = async_session

    assert processed == 2

    # After ack, the pending list should be empty.
    pending = await client.xpending(PORTAL_EVENTS_STREAM, CONSUMER_GROUP)
    # xpending returns {'pending': 0, ...} when empty.
    pending_count = pending.get("pending", 0) if isinstance(pending, dict) else pending[0]
    assert pending_count == 0

    # State changes applied.
    from sqlalchemy import select
    from models.tenant import Tenant
    t = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    # Last write wins; subscription.upgraded ran after tenant.suspended, but
    # subscription.upgraded doesn't touch is_active, only plan/limits.
    assert t.is_active is False  # set by tenant.suspended
    assert t.plan_slug == "pro"  # set by subscription.upgraded
    assert t.max_users == 50


async def test_consumer_empty_batch_returns_zero(db):
    bus = _FakeBus()
    await bus.ensure_consumer_group(PORTAL_EVENTS_STREAM, CONSUMER_GROUP)

    import services.events.consumer as consumer_mod
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session_cm():
        yield db

    consumer_mod.async_session = _session_cm
    try:
        # block_ms=10 so the test doesn't hang.
        processed = await _process_batch(bus, "test-1", count=10, block_ms=10)
    finally:
        from core.database import async_session
        consumer_mod.async_session = async_session
    assert processed == 0
