"""
Sentry initialization + per-request scope enrichment (v3 §15.5).

Each exception sent to Sentry is tagged with `service`, `tenant_id`, and
`trace_id` so the platform's Sentry org can group / drill down per product
and per tenant.

init_sentry() is a no-op when SENTRY_DSN is empty (dev default) — the
module can be imported safely from anywhere.

SentryContextMiddleware pushes a Sentry scope per request and writes the
tags. It MUST run after TraceMiddleware so request.state.trace_id is set,
but BEFORE handlers (so exceptions raised inside a handler see the tags).

Tenant_id is extracted from the unverified JWT (labeling only — never use
this for authorization). Anonymous requests stay as "anonymous".
"""
from __future__ import annotations

from typing import Optional

import jwt
import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware  # noqa: F401 — re-export
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import get_settings
from core.logger import get_logger

logger = get_logger()
settings = get_settings()


def init_sentry() -> bool:
    """Returns True if Sentry was initialized, False if DSN was empty.
    Safe to call multiple times — Sentry's init is idempotent.
    """
    if not settings.SENTRY_DSN:
        return False

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        release=settings.SENTRY_RELEASE or None,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Send PII (user, IP) only when explicitly enabled at the DSN level.
        send_default_pii=False,
    )
    sentry_sdk.set_tag("service", settings.PRODUCT_SLUG)
    logger.info(
        "sentry_initialized",
        environment=settings.SENTRY_ENVIRONMENT,
        product=settings.PRODUCT_SLUG,
    )
    return True


def _extract_tenant_id(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    except jwt.PyJWTError:
        return None
    tid = claims.get("tenant_id")
    return tid if isinstance(tid, str) and tid else None


def _extract_user_id(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    try:
        claims = jwt.decode(
            auth[7:].strip(),
            options={"verify_signature": False, "verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) and sub else None


class SentryContextMiddleware(BaseHTTPMiddleware):
    """Attach tenant_id / trace_id / user_id to the current Sentry scope.
    Runs even when Sentry isn't initialized — sentry_sdk APIs are no-ops
    in that case, so we don't pay extra branching here.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        with sentry_sdk.new_scope() as scope:
            tenant_id = _extract_tenant_id(request) or "anonymous"
            scope.set_tag("tenant_id", tenant_id)
            trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-ID")
            if trace_id:
                scope.set_tag("trace_id", trace_id)
            user_id = _extract_user_id(request)
            if user_id:
                scope.set_user({"id": user_id})
            return await call_next(request)
