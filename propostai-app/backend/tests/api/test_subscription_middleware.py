"""
Tests for SubscriptionMiddleware (v3 §11, §14).

Strategy: override app.state.subscription_state_loader to return precomputed
tenant state without touching the DB. The middleware extracts tenant_id
from the JWT (no signature check) so we can mint tokens with PyJWT directly.

Covers:
  - Public paths bypass (no token, no DB hit)
  - Authenticated active tenant → passes through
  - Suspended tenant + safe method (GET) → passes through
  - Suspended tenant + unsafe method (POST) → 423
  - Unknown tenant → 403 tenant_not_found
  - Portal/LGPD paths bypass even when suspended
"""
from __future__ import annotations

import jwt
import pytest

from core.config import get_settings
from core.subscription_middleware import (
    _tenant_cache,
    invalidate_tenant_state_cache,
)

pytestmark = pytest.mark.api

settings = get_settings()


def _token(tenant_id: str) -> str:
    return jwt.encode(
        {"sub": "user-1", "tenant_id": tenant_id, "exp": 9_999_999_999},
        "irrelevant-test-secret",
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    _tenant_cache._store.clear()
    yield
    _tenant_cache._store.clear()


@pytest.fixture
def loader(client):
    """Install a state loader and return the table so tests can mutate it."""
    from main import app

    table: dict[str, tuple[bool, str | None]] = {}

    def _load(tenant_id: str):
        return table.get(tenant_id)

    app.state.subscription_state_loader = _load
    yield table
    delattr(app.state, "subscription_state_loader")


# ── bypass ──────────────────────────────────────────────────────────────────


async def test_health_bypasses_middleware(client, loader):
    # No tenant_id in the loader — would 403 if middleware did anything.
    r = await client.get("/health")
    assert r.status_code == 200


async def test_no_auth_header_bypasses(client, loader):
    # Anonymous request: middleware lets it through; downstream auth handles 401.
    r = await client.get("/api/v1/proposals")
    # Either 401 (auth fired) or some non-423 status — never blocked by us.
    assert r.status_code != 423
    assert r.status_code != 403 or "tenant_not_found" not in (r.json().get("detail") or "")


# ── active tenant ────────────────────────────────────────────────────────────


async def test_active_tenant_allowed(client, loader):
    loader["tenant-active"] = (True, None)
    headers = {"Authorization": f"Bearer {_token('tenant-active')}"}
    r = await client.get("/api/v1/proposals", headers=headers)
    # Middleware passes; whatever downstream returns is fine (likely 401/422/...).
    assert r.status_code != 423


# ── suspended tenant ─────────────────────────────────────────────────────────


async def test_suspended_tenant_blocks_writes(client, loader):
    loader["tenant-suspended"] = (False, "non-payment")
    headers = {"Authorization": f"Bearer {_token('tenant-suspended')}"}
    r = await client.post("/api/v1/proposals", json={}, headers=headers)
    assert r.status_code == 423
    body = r.json()
    assert body["code"] == "tenant_suspended"
    assert body["reason"] == "non-payment"


async def test_suspended_tenant_allows_reads(client, loader):
    loader["tenant-suspended"] = (False, "non-payment")
    headers = {"Authorization": f"Bearer {_token('tenant-suspended')}"}
    r = await client.get("/api/v1/proposals", headers=headers)
    assert r.status_code != 423


# ── unknown tenant ───────────────────────────────────────────────────────────


async def test_unknown_tenant_blocked(client, loader):
    headers = {"Authorization": f"Bearer {_token('ghost')}"}
    r = await client.post("/api/v1/proposals", json={}, headers=headers)
    assert r.status_code == 403
    assert r.json()["code"] == "tenant_not_found"


# ── HMAC paths bypass even when "suspended" ──────────────────────────────────


async def test_portal_provision_bypasses_middleware(client, loader):
    # Suspended state would block POSTs to non-bypass paths.
    loader["t1"] = (False, "suspended")
    # No token — but provisioning paths don't carry one anyway.
    r = await client.post("/api/v1/integrations/portal/provision", json={})
    # 401 from HMAC (no signature), NOT 423 from middleware.
    assert r.status_code != 423


async def test_lgpd_bypasses_middleware(client, loader):
    loader["t1"] = (False, "suspended")
    r = await client.post("/api/v1/lgpd/delete-tenant", json={})
    assert r.status_code != 423


# ── cache hygiene ────────────────────────────────────────────────────────────


async def test_invalidate_cache_helper(client, loader):
    loader["tenant-x"] = (True, None)
    headers = {"Authorization": f"Bearer {_token('tenant-x')}"}
    await client.get("/api/v1/proposals", headers=headers)
    assert _tenant_cache.get("tenant-x") == (True, None)

    invalidate_tenant_state_cache("tenant-x")
    assert _tenant_cache.get("tenant-x") is None
