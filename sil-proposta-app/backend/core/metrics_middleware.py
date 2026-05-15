"""
Prometheus metrics middleware — records http_requests_total and
http_request_duration_seconds (v3 §15.3).

Runs after Trace + Subscription so:
  - trace_id is already in contextvars (no use here, but consistent)
  - blocked-by-subscription responses (423) are still counted (good — we
    want visibility into how often suspended tenants try to write)
  - failed-auth responses (401) are still counted

The `path` label uses the matched route template
(`/api/v1/proposals/{proposal_id}`) rather than the literal URL, to keep
cardinality bounded. Falls back to the literal path when no route matched
(404s, mostly).

`tenant_id` is taken from the JWT when available, "anonymous" otherwise.
The middleware does NOT verify the signature — it only extracts the claim
for labeling, mirroring SubscriptionMiddleware's approach.

`/metrics` itself is excluded from the counters; otherwise Prometheus
scraping inflates its own numbers.
"""
from __future__ import annotations

import time
from typing import Optional

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.logger import get_logger
from core.metrics import http_request_duration_seconds, http_requests_total

logger = get_logger()


EXCLUDED_PATHS = {"/metrics"}


def _extract_tenant_id(request: Request) -> str:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return "anonymous"
    token = auth[7:].strip()
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    except jwt.PyJWTError:
        return "anonymous"
    tid = claims.get("tenant_id")
    return tid if isinstance(tid, str) and tid else "anonymous"


def _route_pattern(request: Request) -> str:
    """Return the matched route template if FastAPI populated it.

    Starlette stashes the matched `route` object on request.scope["route"]
    AFTER the router runs — which is AFTER middleware enters but BEFORE
    middleware exits. So this is safe to read once call_next returns.
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in EXCLUDED_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response: Optional[Response] = None
        status_code = 500  # default if call_next raises
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            label_path = _route_pattern(request)
            tenant_id = _extract_tenant_id(request)
            http_requests_total.labels(
                method=request.method,
                path=label_path,
                status=str(status_code),
                tenant_id=tenant_id,
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                path=label_path,
            ).observe(duration)
