"""
Prometheus metrics registry (v3 §15.3).

Exposes the standard `{produto}_*` metric set required by the platform:
  - {slug}_http_requests_total{method, path, status, tenant_id}
  - {slug}_http_request_duration_seconds_bucket{method, path}
  - {slug}_proposals_generated_total{tenant_id}
  - {slug}_ps_documents_exported_total{tenant_id}

Path label uses the matched route pattern (`/api/v1/proposals/{proposal_id}`)
rather than the literal URL — otherwise high-cardinality IDs blow up the
metrics endpoint. The MetricsMiddleware sets that label from request.scope.

A dedicated CollectorRegistry instance is used so test fixtures can reset
it between tests without touching the global registry that ASGI lifespans
might share with other processes. The default Counter/Histogram still
attach to the module-level registry; we expose helpers to render and
reset.
"""
from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from core.config import get_settings

settings = get_settings()


# Buckets in seconds; default Prometheus buckets + a few tuned for our
# typical request profile (most calls < 200ms; AI generation 2–60s).
_BUCKETS = (0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)


def _slug() -> str:
    # Sanitize the product slug for use as a Prometheus name prefix
    # (only [a-zA-Z_:][a-zA-Z0-9_:]* allowed).
    return settings.PRODUCT_SLUG.replace("-", "_")


registry = CollectorRegistry()


http_requests_total = Counter(
    f"{_slug()}_http_requests_total",
    "HTTP requests served, partitioned by method/route/status/tenant.",
    labelnames=("method", "path", "status", "tenant_id"),
    registry=registry,
)

http_request_duration_seconds = Histogram(
    f"{_slug()}_http_request_duration_seconds",
    "HTTP request handler duration in seconds.",
    labelnames=("method", "path"),
    buckets=_BUCKETS,
    registry=registry,
)

proposals_generated_total = Counter(
    f"{_slug()}_proposals_generated_total",
    "Proposals successfully generated.",
    labelnames=("tenant_id",),
    registry=registry,
)

ps_documents_exported_total = Counter(
    f"{_slug()}_ps_documents_exported_total",
    "PS (Proposta de Solução) Word documents exported.",
    labelnames=("tenant_id",),
    registry=registry,
)

wp_documents_exported_total = Counter(
    f"{_slug()}_wp_documents_exported_total",
    "WP Excel work packages exported.",
    labelnames=("tenant_id",),
    registry=registry,
)


def render_metrics() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    return generate_latest(registry), CONTENT_TYPE_LATEST


def reset_for_tests() -> None:
    """Tests can call this between cases to reset counter state."""
    # Clearing samples by re-instantiating would change identities; instead
    # we clear the internal `_metrics` dict on each labeled collector. This
    # is private API but stable across prometheus_client 0.20.
    for collector in (
        http_requests_total,
        http_request_duration_seconds,
        proposals_generated_total,
        ps_documents_exported_total,
        wp_documents_exported_total,
    ):
        collector._metrics.clear()  # type: ignore[attr-defined]
