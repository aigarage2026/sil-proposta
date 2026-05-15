"""
SubscriptionMiddleware — enforce tenant state on every authenticated request
(v3 §11 `tenant.suspended` → read-only, v3 §14 agn-middleware).

Decision matrix:
    tenant.is_active = True              → allow
    tenant.is_active = False (suspended) → read-only:
        - safe methods (GET, HEAD, OPTIONS) → allow
        - unsafe (POST, PUT, PATCH, DELETE) → 423 Locked

Bypassed entirely (no JWT inspection, no DB lookup):
    - Public/system paths: /, /health, /docs, /redoc, /openapi.json,
      /.well-known/*
    - Auth paths: /auth/* (login/refresh — a suspended tenant must still
      be able to log in to see the suspension reason in the UI)
    - HMAC-protected Portal paths: /api/v1/integrations/portal/*,
      /api/v1/lgpd/* (the Portal is the *authority* on tenant state —
      it must always be able to call these)

When the request has no Authorization header (anonymous), we bypass —
downstream auth dependencies will return 401 themselves.

A tiny in-process TTL cache (default 30s) keeps the DB hit cost low. The
event consumer for `tenant.suspended` (Onda 3) will invalidate this cache
on state change; until then, 30s of staleness is acceptable.
"""
from __future__ import annotations

import time
from typing import Optional

import jwt
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core.config import get_settings
from core.database import async_session
from core.logger import get_logger
from models.tenant import Tenant

logger = get_logger()
settings = get_settings()


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

BYPASS_EXACT = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}

BYPASS_PREFIXES = (
    "/.well-known/",
    "/auth/",
    "/setup/",
    "/api/v1/integrations/portal/",
    "/api/v1/lgpd/",
)


class _TenantStateCache:
    """Tiny TTL cache for (is_active, suspension_reason).
    Process-local; invalidated by event handlers in Onda 3.
    """

    def __init__(self, ttl_seconds: int = 30):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, bool, Optional[str]]] = {}

    def get(self, tenant_id: str) -> Optional[tuple[bool, Optional[str]]]:
        entry = self._store.get(tenant_id)
        if not entry:
            return None
        expires_at, is_active, reason = entry
        if expires_at < time.monotonic():
            self._store.pop(tenant_id, None)
            return None
        return is_active, reason

    def put(self, tenant_id: str, is_active: bool, reason: Optional[str]) -> None:
        self._store[tenant_id] = (time.monotonic() + self._ttl, is_active, reason)

    def invalidate(self, tenant_id: str) -> None:
        self._store.pop(tenant_id, None)


_tenant_cache = _TenantStateCache()


def invalidate_tenant_state_cache(tenant_id: str) -> None:
    """Public hook for the event consumer (`tenant.suspended`,
    `subscription.upgraded`, etc.) to clear stale cache entries.
    """
    _tenant_cache.invalidate(tenant_id)


def _should_bypass(path: str) -> bool:
    if path in BYPASS_EXACT:
        return True
    return any(path.startswith(p) for p in BYPASS_PREFIXES)


def _extract_tenant_id(request: Request) -> Optional[str]:
    """Pull tenant_id from a Bearer JWT *without* verifying — signature
    will be re-checked downstream by the auth dependency. We just need a
    routing key for the suspension check.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    try:
        # Skip signature/iss/aud — those are enforced by decode_token().
        claims = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
    except jwt.PyJWTError:
        return None
    tid = claims.get("tenant_id")
    return tid if isinstance(tid, str) and tid else None


async def _load_tenant_state_from_db(tenant_id: str) -> Optional[tuple[bool, Optional[str]]]:
    async with async_session() as db:
        result = await db.execute(
            select(Tenant.is_active, Tenant.suspension_reason).where(Tenant.id == tenant_id)
        )
        row = result.first()
    if not row:
        return None
    return bool(row[0]), row[1]


async def _load_tenant_state(
    request: Request, tenant_id: str
) -> Optional[tuple[bool, Optional[str]]]:
    cached = _tenant_cache.get(tenant_id)
    if cached is not None:
        return cached

    # Tests can override via app.state.subscription_state_loader — a
    # callable (tenant_id) -> Optional[(bool, str|None)], sync or async.
    loader = getattr(request.app.state, "subscription_state_loader", None)
    if loader is not None:
        result = loader(tenant_id)
        if hasattr(result, "__await__"):
            result = await result
    else:
        result = await _load_tenant_state_from_db(tenant_id)

    if result is None:
        return None
    is_active, reason = result
    _tenant_cache.put(tenant_id, is_active, reason)
    return is_active, reason


class SubscriptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if _should_bypass(path):
            return await call_next(request)

        tenant_id = _extract_tenant_id(request)
        if not tenant_id:
            # Anonymous — let downstream auth deal with it.
            return await call_next(request)

        state = await _load_tenant_state(request, tenant_id)
        if state is None:
            # Token points at a tenant that no longer exists.
            logger.warning("subscription_tenant_not_found", tenant_id=tenant_id, path=path)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Tenant nao encontrado",
                    "code": "tenant_not_found",
                },
            )

        is_active, reason = state
        if is_active:
            return await call_next(request)

        # Suspended: allow read-only methods.
        if request.method in SAFE_METHODS:
            return await call_next(request)

        logger.info(
            "subscription_blocked_write",
            tenant_id=tenant_id,
            path=path,
            method=request.method,
            reason=reason,
        )
        return JSONResponse(
            status_code=423,
            content={
                "detail": "Tenant suspenso — apenas leitura disponivel",
                "code": "tenant_suspended",
                "reason": reason,
            },
        )
