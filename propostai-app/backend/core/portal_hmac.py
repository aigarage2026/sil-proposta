"""
HMAC validation for endpoints called *by* the Portal (v3 §4.1, §16.5).

The Portal triggers per-tenant operations on each product: provisioning,
deprovisioning, LGPD delete/export, backup snapshot/restore. Those
endpoints are NOT user-facing — there's no JWT — and need a different
authentication channel:

    Header:  X-Portal-Signature: <hex hmac-sha256>
    Body:    raw request body
    Secret:  PORTAL_HMAC_SECRET (shared between Portal and product)

Constant-time comparison via hmac.compare_digest. Disabled when
PORTAL_HMAC_SECRET is empty (dev convenience): the dependency just logs
a warning and lets the request through. In production, leaving the
secret empty and exposing these endpoints to the internet would be a
critical mistake — the SubscriptionMiddleware (block 12) and Nginx
gateway should also restrict their reachability.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request, status

from core.config import get_settings
from core.logger import get_logger

settings = get_settings()
logger = get_logger()


def _compute_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def require_portal_hmac(request: Request) -> None:
    """Dependency: 401 unless X-Portal-Signature matches HMAC(body)."""
    secret = settings.PORTAL_HMAC_SECRET
    if not secret:
        logger.warning(
            "portal_hmac_disabled",
            reason="PORTAL_HMAC_SECRET is empty",
            path=str(request.url.path),
        )
        return

    provided = request.headers.get("X-Portal-Signature", "")
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Portal-Signature header",
        )

    body = await request.body()
    expected = _compute_signature(body, secret)
    if not hmac.compare_digest(provided, expected):
        # Don't leak the expected value back to the caller.
        logger.warning(
            "portal_hmac_mismatch",
            path=str(request.url.path),
            provided_prefix=provided[:8],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Portal-Signature",
        )


def sign_request_body(body: bytes, secret: str | None = None) -> str:
    """Helper for tests / Portal-side signing. Not used by the runtime."""
    return _compute_signature(body, secret or settings.PORTAL_HMAC_SECRET)
