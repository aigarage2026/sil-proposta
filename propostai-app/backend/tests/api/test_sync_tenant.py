"""
REST fallback for portal.events — POST /api/v1/integrations/portal/sync-tenant.

Per §21.2.3: when B4 (Redis Streams `portal.events`) is 🔴 not yet
available, the Portal can deliver events via this REST endpoint and the
product applies them the same way the consumer would.
"""
import json

import pytest
from sqlalchemy import select

from core.config import get_settings
from core.portal_hmac import sign_request_body
from models.tenant import Tenant

pytestmark = pytest.mark.api

settings = get_settings()


def _sign(body: dict, secret: str = "test-portal-secret") -> tuple[bytes, dict]:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    sig = sign_request_body(raw, secret)
    return raw, {"X-Portal-Signature": sig, "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _hmac_secret(monkeypatch):
    monkeypatch.setattr(settings, "PORTAL_HMAC_SECRET", "test-portal-secret")
    yield


async def test_sync_tenant_applies_suspended_event(client, sap_world, db):
    tid = sap_world["tenant"].id
    body = {
        "type": "tenant.suspended",
        "tenant_id": tid,
        "payload": {"reason": "non-payment"},
    }
    raw, headers = _sign(body)
    r = await client.post("/api/v1/integrations/portal/sync-tenant", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "applied", "type": "tenant.suspended"}

    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.is_active is False
    assert reloaded.suspension_reason == "non-payment"


async def test_sync_tenant_applies_subscription_upgrade(client, sap_world, db):
    tid = sap_world["tenant"].id
    body = {
        "type": "subscription.upgraded",
        "tenant_id": tid,
        "payload": {"plan_slug": "pro", "max_users": 25},
    }
    raw, headers = _sign(body)
    r = await client.post("/api/v1/integrations/portal/sync-tenant", content=raw, headers=headers)
    assert r.status_code == 200

    reloaded = (await db.execute(select(Tenant).where(Tenant.id == tid))).scalar_one()
    assert reloaded.plan_slug == "pro"
    assert reloaded.max_users == 25


async def test_sync_tenant_missing_signature(client, sap_world):
    body = {"type": "tenant.suspended", "tenant_id": sap_world["tenant"].id}
    r = await client.post("/api/v1/integrations/portal/sync-tenant", json=body)
    assert r.status_code == 401


async def test_sync_tenant_unknown_type_is_applied_noop(client):
    body = {"type": "totally.unknown", "tenant_id": "x"}
    raw, headers = _sign(body)
    r = await client.post("/api/v1/integrations/portal/sync-tenant", content=raw, headers=headers)
    # Unknown types are no-ops (so handler set evolution doesn't break Portal).
    assert r.status_code == 200
    assert r.json()["status"] == "applied"
