"""
JWKS client — fetches and caches the Portal's public signing keys.

This is the v3 §6 mechanism for federated identity: the Portal owns the
private RS256 key and publishes the public set at
`/.well-known/jwks.json`. Each product (this one) validates incoming
tokens locally by looking up the key id (`kid`) in the cached JWKS.

Until the Portal exposes the endpoint, this client is a no-op stub that
will start working as soon as PORTAL_API_URL points to a real Portal
instance. The decode path (core/security.decode_token) automatically
falls back to local HS256 validation when JWKS lookup is disabled or
fails — see "dual mode" in the v3 §6.5 migration path.

Cache: in-memory only. We deliberately avoid Redis here to keep this
module dependency-free and to make startup tolerant to Redis outages.
The Portal's JWKS is small (a few hundred bytes per key) and rotation
is infrequent (§6.4: 7-day overlap), so an in-memory TTL of 24h is
plenty.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx
import jwt

from core.config import get_settings
from core.logger import get_logger

settings = get_settings()
logger = get_logger()


class JWKSClient:
    """Fetches the Portal JWKS and resolves signing keys by kid.

    Thread-safety: a single asyncio.Lock guards the refresh path so that
    a burst of validations after cache expiry only triggers one HTTP fetch.
    """

    def __init__(
        self,
        jwks_url: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        # Default URL is derived from PORTAL_API_URL. Empty string disables.
        self._jwks_url = jwks_url if jwks_url is not None else self._default_jwks_url()
        self._cache_ttl = cache_ttl_seconds or settings.PORTAL_JWKS_CACHE_TTL_SECONDS
        self._timeout = request_timeout_seconds

        self._cached_jwks: Optional[dict[str, Any]] = None
        self._cached_at: float = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def _default_jwks_url() -> str:
        base = (settings.PORTAL_API_URL or "").rstrip("/")
        if not base:
            return ""
        return f"{base}/.well-known/jwks.json"

    @property
    def enabled(self) -> bool:
        """JWKS lookup is enabled iff a JWKS URL is configured."""
        return bool(self._jwks_url)

    async def get_signing_key(self, kid: str) -> Optional[Any]:
        """Returns the public key for `kid`, or None if not found / disabled.

        On cache miss, refetches the JWKS once (locked) and tries again.
        """
        if not self.enabled:
            return None

        key = self._lookup_in_cache(kid)
        if key is not None:
            return key

        # Cache miss or expired — refresh and retry.
        await self._refresh()
        return self._lookup_in_cache(kid)

    def _lookup_in_cache(self, kid: str) -> Optional[Any]:
        if self._cached_jwks is None:
            return None
        if (time.monotonic() - self._cached_at) > self._cache_ttl:
            return None
        for jwk in self._cached_jwks.get("keys", []):
            if jwk.get("kid") == kid:
                # PyJWKClient expects a JWK in dict form; we use PyJWT's
                # built-in algorithms.RSAAlgorithm.from_jwk for parsing.
                return jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
        return None

    async def _refresh(self) -> None:
        async with self._lock:
            # Re-check inside the lock — another task may have refreshed already.
            if self._cached_jwks is not None and (
                time.monotonic() - self._cached_at
            ) <= self._cache_ttl:
                return
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(self._jwks_url)
                    response.raise_for_status()
                    self._cached_jwks = response.json()
                    self._cached_at = time.monotonic()
                    logger.info(
                        "jwks_refreshed",
                        url=self._jwks_url,
                        key_count=len(self._cached_jwks.get("keys", [])),
                    )
            except Exception as e:  # noqa: BLE001
                # Failure to fetch is non-fatal: decode_token will fall
                # back to HS256 if dual mode is on, or fail with a clear
                # error if not.
                logger.warning("jwks_refresh_failed", url=self._jwks_url, error=str(e))


_singleton: Optional[JWKSClient] = None


def get_jwks_client() -> JWKSClient:
    """Process-wide singleton."""
    global _singleton
    if _singleton is None:
        _singleton = JWKSClient()
    return _singleton
