"""
Metrics middleware + /metrics endpoint (v3 §15.3).

Verifies:
  - /metrics returns Prometheus exposition format with our counters defined
  - Hitting an endpoint increments http_requests_total with the right labels
  - /metrics itself is excluded from the counters
  - JWT tenant_id is used as the label; missing/invalid token → "anonymous"
  - Route template (not literal URL) is used as the path label so IDs don't blow up cardinality
"""
import jwt
import pytest

from core import metrics as metrics_mod

pytestmark = pytest.mark.api


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics_mod.reset_for_tests()
    yield
    metrics_mod.reset_for_tests()


def _token(tenant_id: str = "t-metrics") -> str:
    return jwt.encode(
        {"sub": "u-1", "tenant_id": tenant_id, "exp": 9_999_999_999},
        "irrelevant-secret",
        algorithm="HS256",
    )


# ── /metrics endpoint ───────────────────────────────────────────────────────


async def test_metrics_endpoint_returns_prometheus_format(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Prometheus exposition is text/plain with HELP and TYPE lines.
    assert "# HELP" in body
    assert "# TYPE" in body
    # Our slug-prefixed metrics are present.
    assert "sil_proposta_http_requests_total" in body
    assert "sil_proposta_http_request_duration_seconds" in body


async def test_metrics_endpoint_is_not_counted_in_requests_total(client):
    await client.get("/metrics")
    await client.get("/metrics")
    r = await client.get("/metrics")
    # Look for our endpoint in the output — it should NOT appear.
    assert 'path="/metrics"' not in r.text


# ── http_requests_total increments ──────────────────────────────────────────


async def test_health_request_increments_counter(client):
    await client.get("/health")
    r = await client.get("/metrics")
    # /health uses literal path (no route template parameters)
    assert 'path="/health"' in r.text
    assert 'method="GET"' in r.text
    assert 'status="200"' in r.text
    # No auth header → tenant_id="anonymous"
    assert 'tenant_id="anonymous"' in r.text


async def test_route_template_used_as_path_label(client):
    # Hit a route with a path parameter; cardinality should bind to
    # the matched template, not the literal id.
    await client.get("/api/v1/proposals/abc-123-id")
    r = await client.get("/metrics")
    # The literal id should NOT appear as a label value.
    assert "abc-123-id" not in r.text


async def test_jwt_tenant_id_propagates_to_label(client):
    # Use a path that's bypassed by SubscriptionMiddleware so we don't
    # need a tenant lookup — /health is in BYPASS_EXACT but doesn't carry
    # auth. Use a setup path instead.
    headers = {"Authorization": f"Bearer {_token('tenant-XYZ')}"}
    await client.get("/health", headers=headers)
    r = await client.get("/metrics")
    assert 'tenant_id="tenant-XYZ"' in r.text


async def test_invalid_token_falls_back_to_anonymous(client):
    headers = {"Authorization": "Bearer not-a-jwt"}
    await client.get("/health", headers=headers)
    r = await client.get("/metrics")
    assert 'tenant_id="anonymous"' in r.text


# ── histogram observation ───────────────────────────────────────────────────


async def test_duration_histogram_records_buckets(client):
    await client.get("/health")
    r = await client.get("/metrics")
    # Histogram emits *_bucket, *_count, *_sum lines.
    assert "sil_proposta_http_request_duration_seconds_bucket" in r.text
    assert "sil_proposta_http_request_duration_seconds_count" in r.text
    assert "sil_proposta_http_request_duration_seconds_sum" in r.text
