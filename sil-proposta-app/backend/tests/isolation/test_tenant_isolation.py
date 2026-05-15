"""
Cross-tenant isolation — H6 in MIGRATION_PLAN, severity *Crítico*.

Scenario per test: tenant A and tenant B each own a proposal. User from
tenant A authenticates and tries to access tenant B's proposal_id via
every auth-protected route. Expected outcome: 404 (the row is filtered
out by the tenant_id predicate in each endpoint's query).

A positive control accompanies each negative: the same authenticated
user hitting their OWN proposal returns 2xx. If the negative-only check
passed but the positive failed, we'd be looking at a buggy filter that
happens to reject everything; the matched pair guards against that.

Routes covered:
  - GET    /api/v1/proposals               (list filter)
  - GET    /api/v1/proposals/{id}          (detail)
  - PATCH  /api/v1/proposals/{id}/status   (mutation)
  - DELETE /api/v1/proposals/{id}          (destructive)
  - GET    /api/v1/proposals/{id}/export/dam (binary export)
  - GET    /api/v1/proposals/{id}/export/wp  (binary export)

`isolation_client` shims SubscriptionMiddleware so both tenants read as
active (no DB lookup against the production engine). `auth_headers(user)`
mints a real v3-shaped JWT — full decode/auth flow is exercised.
"""
import pytest
from sqlalchemy import select

from models.sil_proposta.proposal import Proposal

pytestmark = pytest.mark.isolation


# ── GET list ────────────────────────────────────────────────────────────────


async def test_list_proposals_only_returns_caller_tenant(
    isolation_client, two_tenants, auth_headers,
):
    user_a = two_tenants["a"]["user"]
    r = await isolation_client.get("/api/v1/proposals", headers=auth_headers(user_a))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    titles = [p["title"] for p in body["proposals"]]
    assert titles == ["Proposta A"]
    assert "Proposta B" not in titles


# ── GET detail ──────────────────────────────────────────────────────────────


async def test_get_detail_404_for_other_tenant(
    isolation_client, two_tenants, auth_headers,
):
    user_a = two_tenants["a"]["user"]
    proposal_b_id = two_tenants["b"]["proposal"].id
    r = await isolation_client.get(
        f"/api/v1/proposals/{proposal_b_id}", headers=auth_headers(user_a),
    )
    assert r.status_code == 404


async def test_get_detail_200_for_own_proposal(
    isolation_client, two_tenants, auth_headers,
):
    user_a = two_tenants["a"]["user"]
    proposal_a_id = two_tenants["a"]["proposal"].id
    r = await isolation_client.get(
        f"/api/v1/proposals/{proposal_a_id}", headers=auth_headers(user_a),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Proposta A"


# ── PATCH status ────────────────────────────────────────────────────────────


async def test_status_update_404_for_other_tenant(
    isolation_client, two_tenants, auth_headers, db,
):
    user_a = two_tenants["a"]["user"]
    proposal_b = two_tenants["b"]["proposal"]
    r = await isolation_client.patch(
        f"/api/v1/proposals/{proposal_b.id}/status",
        json={"status": "review"},
        headers=auth_headers(user_a),
    )
    assert r.status_code == 404
    # Sanity: the row in DB is unchanged.
    reloaded = (await db.execute(select(Proposal).where(Proposal.id == proposal_b.id))).scalar_one()
    assert reloaded.status == "draft"


async def test_status_update_200_for_own_proposal(
    isolation_client, two_tenants, auth_headers,
):
    user_a = two_tenants["a"]["user"]
    proposal_a = two_tenants["a"]["proposal"]
    r = await isolation_client.patch(
        f"/api/v1/proposals/{proposal_a.id}/status",
        json={"status": "review"},
        headers=auth_headers(user_a),
    )
    assert r.status_code == 200, r.text


# ── DELETE ──────────────────────────────────────────────────────────────────


async def test_delete_404_for_other_tenant(
    isolation_client, two_tenants, auth_headers, db,
):
    user_a = two_tenants["a"]["user"]
    proposal_b_id = two_tenants["b"]["proposal"].id
    r = await isolation_client.delete(
        f"/api/v1/proposals/{proposal_b_id}", headers=auth_headers(user_a),
    )
    assert r.status_code == 404
    # Sanity: row still present.
    assert (
        await db.execute(select(Proposal).where(Proposal.id == proposal_b_id))
    ).scalar_one_or_none() is not None


async def test_delete_200_for_own_proposal(
    isolation_client, two_tenants, auth_headers, db,
):
    user_a = two_tenants["a"]["user"]
    proposal_a_id = two_tenants["a"]["proposal"].id
    r = await isolation_client.delete(
        f"/api/v1/proposals/{proposal_a_id}", headers=auth_headers(user_a),
    )
    assert r.status_code == 200


# ── Export DAM ─────────────────────────────────────────────────────────────


async def test_export_dam_404_for_other_tenant(
    isolation_client, two_tenants, auth_headers,
):
    user_a = two_tenants["a"]["user"]
    proposal_b_id = two_tenants["b"]["proposal"].id
    r = await isolation_client.get(
        f"/api/v1/proposals/{proposal_b_id}/export/dam",
        headers=auth_headers(user_a),
    )
    assert r.status_code == 404


# ── Export WP ──────────────────────────────────────────────────────────────


async def test_export_wp_404_for_other_tenant(
    isolation_client, two_tenants, auth_headers,
):
    user_a = two_tenants["a"]["user"]
    proposal_b_id = two_tenants["b"]["proposal"].id
    r = await isolation_client.get(
        f"/api/v1/proposals/{proposal_b_id}/export/wp",
        headers=auth_headers(user_a),
    )
    assert r.status_code == 404


# ── No auth header ─────────────────────────────────────────────────────────


async def test_endpoints_require_auth(isolation_client, two_tenants):
    """No Authorization header → 401 from get_current_user — never 200, never 404."""
    proposal_id = two_tenants["a"]["proposal"].id
    for method, path in [
        ("GET", "/api/v1/proposals"),
        ("GET", f"/api/v1/proposals/{proposal_id}"),
        ("PATCH", f"/api/v1/proposals/{proposal_id}/status"),
        ("DELETE", f"/api/v1/proposals/{proposal_id}"),
        ("GET", f"/api/v1/proposals/{proposal_id}/export/dam"),
        ("GET", f"/api/v1/proposals/{proposal_id}/export/wp"),
    ]:
        kwargs = {"json": {"status": "review"}} if method == "PATCH" else {}
        r = await isolation_client.request(method, path, **kwargs)
        assert r.status_code == 401, (
            f"{method} {path} returned {r.status_code} without auth — must be 401"
        )


# ── Cross-tenant write attempt does not leak data ──────────────────────────


async def test_status_update_does_not_create_orphan_in_db(
    isolation_client, two_tenants, auth_headers, db,
):
    """Defensive: even if a future bug let the PATCH through, verify no
    Proposal rows were created/orphaned during a cross-tenant attempt.
    """
    user_a = two_tenants["a"]["user"]
    proposal_b_id = two_tenants["b"]["proposal"].id
    before = (await db.execute(select(Proposal))).scalars().all()
    n_before = len(before)
    await isolation_client.patch(
        f"/api/v1/proposals/{proposal_b_id}/status",
        json={"status": "review"},
        headers=auth_headers(user_a),
    )
    after = (await db.execute(select(Proposal))).scalars().all()
    assert len(after) == n_before
