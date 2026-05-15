"""
Tests for LGPD endpoints — /api/v1/lgpd/delete-tenant, /export-tenant (v3 §16.5).

Covers:
  - HMAC-protected: missing signature → 401
  - Invalid signature → 401
  - delete-tenant: existing tenant → cascade delete + counts
  - delete-tenant: unknown tenant → not_found
  - export-tenant: returns serializable payload, strips password_hash
  - export-tenant: unknown tenant → not_found
"""
import json

import pytest

from core.config import get_settings
from core.portal_hmac import sign_request_body

pytestmark = pytest.mark.api

settings = get_settings()


# ── helpers ─────────────────────────────────────────────────────────────────


def _sign(body: dict, secret: str = "test-portal-secret") -> tuple[bytes, dict]:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    sig = sign_request_body(raw, secret)
    return raw, {"X-Portal-Signature": sig, "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def _hmac_secret(monkeypatch):
    monkeypatch.setattr(settings, "PORTAL_HMAC_SECRET", "test-portal-secret")
    yield


# ── delete-tenant ───────────────────────────────────────────────────────────


async def test_delete_tenant_missing_signature(client, sap_world):
    body = {"tenant_id": sap_world["tenant"].id}
    r = await client.post("/api/v1/lgpd/delete-tenant", json=body)
    assert r.status_code == 401
    assert "X-Portal-Signature" in r.json()["detail"]


async def test_delete_tenant_invalid_signature(client, sap_world):
    body = {"tenant_id": sap_world["tenant"].id}
    r = await client.post(
        "/api/v1/lgpd/delete-tenant",
        json=body,
        headers={"X-Portal-Signature": "deadbeef"},
    )
    assert r.status_code == 401


async def test_delete_tenant_success(client, sap_world, db):
    from sqlalchemy import select
    from models.tenant import Tenant
    from models.user import User
    from models.company import Company

    tenant_id = sap_world["tenant"].id
    body = {"tenant_id": tenant_id, "requested_by": "compliance@cast.com", "reason": "art. 18, VI"}
    raw, headers = _sign(body)
    r = await client.post("/api/v1/lgpd/delete-tenant", content=raw, headers=headers)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "deleted"
    assert payload["tenant_id"] == tenant_id
    assert payload["counts"]["users"] == 2  # owner + editor
    assert payload["counts"]["companies"] == 1
    assert payload["deleted_at"] is not None

    # Verify cascade.
    assert (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none() is None
    assert (await db.execute(select(User).where(User.tenant_id == tenant_id))).first() is None
    assert (await db.execute(select(Company).where(Company.tenant_id == tenant_id))).first() is None


async def test_delete_tenant_not_found(client):
    body = {"tenant_id": "ghost-tenant-id"}
    raw, headers = _sign(body)
    r = await client.post("/api/v1/lgpd/delete-tenant", content=raw, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "not_found"


# ── export-tenant ───────────────────────────────────────────────────────────


async def test_export_tenant_success(client, sap_world):
    tenant_id = sap_world["tenant"].id
    body = {"tenant_id": tenant_id, "requested_by": "compliance@cast.com"}
    raw, headers = _sign(body)
    r = await client.post("/api/v1/lgpd/export-tenant", content=raw, headers=headers)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "exported"
    assert payload["exported_at"] is not None

    data = payload["payload"]
    assert data["tenant"]["id"] == tenant_id
    assert len(data["users"]) == 2
    assert len(data["companies"]) == 1

    # Sensitive fields must not leak.
    for u in data["users"]:
        assert "password_hash" not in u


async def test_export_tenant_not_found(client):
    body = {"tenant_id": "ghost-tenant-id"}
    raw, headers = _sign(body)
    r = await client.post("/api/v1/lgpd/export-tenant", content=raw, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "not_found"


async def test_export_tenant_missing_signature(client, sap_world):
    body = {"tenant_id": sap_world["tenant"].id}
    r = await client.post("/api/v1/lgpd/export-tenant", json=body)
    assert r.status_code == 401
