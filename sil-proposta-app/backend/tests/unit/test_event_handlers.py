"""
Unit tests for portal.events handlers (v3 §4.2).

Verifies:
  - Idempotency: same event applied twice → same state, no error
  - tenant.suspended sets is_active=False + invalidates middleware cache
  - tenant.deleted soft-deletes (does NOT remove the row)
  - subscription.upgraded updates plan/limits in place
  - subscription.canceled suspends
  - user.role_changed updates role (skips if user missing)
  - Unknown event type → no-op, returns True (consumer will ack)
  - Missing tenant_id on tenant events → no-op, returns True (poison-safe)
"""
import pytest
from sqlalchemy import select

from core.subscription_middleware import _tenant_cache
from models.tenant import Tenant
from services.events.handlers import dispatch

pytestmark = pytest.mark.unit


async def test_dispatch_unknown_type_is_noop(db):
    result = await dispatch({"type": "completely.unknown"}, db)
    assert result is True


async def test_dispatch_missing_type_is_noop(db):
    result = await dispatch({"tenant_id": "x"}, db)
    assert result is True


# ── tenant.created ──────────────────────────────────────────────────────────


async def test_tenant_created_creates_when_absent(db):
    event = {
        "type": "tenant.created",
        "tenant_id": "new-tenant",
        "slug": "new-tenant",
        "name": "New Tenant Inc.",
        "plan_slug": "pro",
    }
    assert await dispatch(event, db) is True

    found = (await db.execute(select(Tenant).where(Tenant.id == "new-tenant"))).scalar_one()
    assert found.name == "New Tenant Inc."
    assert found.plan_slug == "pro"
    assert found.is_active is True


async def test_tenant_created_is_idempotent(db, sap_world):
    event = {
        "type": "tenant.created",
        "tenant_id": sap_world["tenant"].id,
        "name": "Should Not Override",
    }
    assert await dispatch(event, db) is True
    # Original name preserved (idempotency = skip, not overwrite).
    reloaded = (await db.execute(select(Tenant).where(Tenant.id == sap_world["tenant"].id))).scalar_one()
    assert reloaded.name == "Cast Group Test"


# ── tenant.suspended ────────────────────────────────────────────────────────


async def test_tenant_suspended_blocks_and_invalidates_cache(db, sap_world):
    tid = sap_world["tenant"].id
    _tenant_cache.put(tid, True, None)
    assert _tenant_cache.get(tid) == (True, None)

    event = {"type": "tenant.suspended", "tenant_id": tid, "reason": "non-payment"}
    assert await dispatch(event, db) is True

    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.is_active is False
    assert reloaded.suspension_reason == "non-payment"
    assert _tenant_cache.get(tid) is None  # invalidated


async def test_tenant_suspended_is_idempotent(db, sap_world):
    tid = sap_world["tenant"].id
    event = {"type": "tenant.suspended", "tenant_id": tid, "reason": "x"}
    await dispatch(event, db)
    await dispatch(event, db)
    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.is_active is False


async def test_tenant_suspended_unknown_tenant_is_noop(db):
    event = {"type": "tenant.suspended", "tenant_id": "ghost"}
    assert await dispatch(event, db) is True


# ── tenant.deleted ──────────────────────────────────────────────────────────


async def test_tenant_deleted_soft_deletes(db, sap_world):
    tid = sap_world["tenant"].id
    event = {"type": "tenant.deleted", "tenant_id": tid}
    assert await dispatch(event, db) is True
    # Row still there, just suspended.
    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.is_active is False
    assert reloaded.suspension_reason == "tenant.deleted"


# ── subscription.* ──────────────────────────────────────────────────────────


async def test_subscription_upgraded_updates_limits(db, sap_world):
    tid = sap_world["tenant"].id
    event = {
        "type": "subscription.upgraded",
        "tenant_id": tid,
        "plan_slug": "enterprise",
        "max_users": 100,
        "max_proposals_per_month": 1000,
        "features": {"advanced_rag": True},
    }
    assert await dispatch(event, db) is True

    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.plan_slug == "enterprise"
    assert reloaded.max_users == 100
    assert reloaded.max_proposals_per_month == 1000
    assert reloaded.features == {"advanced_rag": True}


async def test_subscription_upgraded_handles_string_ints(db, sap_world):
    # Streams flatten ints as strings; handler must coerce.
    tid = sap_world["tenant"].id
    event = {
        "type": "subscription.upgraded",
        "tenant_id": tid,
        "max_users": "42",
    }
    assert await dispatch(event, db) is True
    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.max_users == 42


async def test_subscription_canceled_suspends(db, sap_world):
    tid = sap_world["tenant"].id
    event = {"type": "subscription.canceled", "tenant_id": tid}
    assert await dispatch(event, db) is True
    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.is_active is False
    assert reloaded.suspension_reason == "subscription.canceled"


# ── user.role_changed ───────────────────────────────────────────────────────


async def test_user_role_changed_updates_role(db, sap_world):
    user = sap_world["editor"]
    event = {"type": "user.role_changed", "user_id": user.id, "role": "admin"}
    assert await dispatch(event, db) is True
    from models.user import User
    reloaded = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    assert reloaded.role == "admin"


async def test_user_role_changed_unknown_user_is_noop(db):
    event = {"type": "user.role_changed", "user_id": "ghost", "role": "admin"}
    assert await dispatch(event, db) is True


# ── crash safety ────────────────────────────────────────────────────────────


async def test_handler_crash_returns_false(db, monkeypatch):
    # Force the handler to blow up by passing a bad event shape that the
    # SQL layer rejects. We monkey-patch to raise inside handle_tenant_created.
    from services.events import handlers as h

    async def boom(event, db):
        raise RuntimeError("simulated crash")

    monkeypatch.setitem(h.HANDLERS, "tenant.suspended", boom)
    result = await dispatch({"type": "tenant.suspended", "tenant_id": "x"}, db)
    assert result is False  # consumer should NOT ack
