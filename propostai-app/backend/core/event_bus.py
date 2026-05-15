"""
Event bus — Redis Streams primitives (v3 §12.4, §4.2, §4.3).

Thin wrapper around redis.asyncio that gives us:
  - `publish(stream, event)` for emitting `usage.metric`, `audit.action`, etc.
  - `ensure_consumer_group(stream, group)` (idempotent)
  - `read_group(stream, group, consumer, count, block_ms)` for the consumer
  - `ack(stream, group, message_id)`

Streams used:
  - `portal.events` (consumed) — Portal publishes tenant/subscription/user events
  - `propostai.events` (published) — emitted by this product (usage.metric,
    audit.action, health.degraded, tenant.feature_used). Per §16.7 the
    namespace is `{slug}:*` but the v3 examples show `{slug}.events`; we
    follow the example.

The event payload is flat key→string mapping. We JSON-encode non-string
values transparently. `type` is always a string (event kind).
"""
from __future__ import annotations

import json
from typing import Any, Optional

import redis.asyncio as redis_lib

from core.config import get_settings
from core.logger import get_logger

logger = get_logger()
settings = get_settings()


PORTAL_EVENTS_STREAM = "portal.events"
PRODUCT_EVENTS_STREAM = f"{settings.PRODUCT_SLUG}.events"
CONSUMER_GROUP = f"{settings.PRODUCT_SLUG}-consumers"


def _flatten(payload: dict[str, Any]) -> dict[str, str]:
    """XADD fields must be flat string→string. Non-string values are JSON-encoded.
    Booleans become 'true'/'false' so the consumer can json.loads() them back.
    """
    out: dict[str, str] = {}
    for k, v in payload.items():
        if v is None:
            continue
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, (int, float)):
            out[k] = str(v)
        else:
            out[k] = json.dumps(v, default=str)
    return out


def _unflatten(fields: dict[str, str]) -> dict[str, Any]:
    """Inverse of _flatten: try to JSON-decode each value, keeping the
    original string on failure (most fields are plain strings — tenant_id,
    type, etc.).
    """
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if not isinstance(v, str):
            out[k] = v
            continue
        if v in ("true", "false"):
            out[k] = v == "true"
            continue
        # Try JSON only if it looks structured.
        if v and v[0] in "[{\"":
            try:
                out[k] = json.loads(v)
                continue
            except (json.JSONDecodeError, ValueError):
                pass
        out[k] = v
    return out


class EventBus:
    """Lazy-initialized Redis client + xadd/xreadgroup helpers."""

    def __init__(self, url: Optional[str] = None):
        self._url = url or settings.REDIS_URL
        self._client: Optional[redis_lib.Redis] = None

    async def client(self) -> redis_lib.Redis:
        if self._client is None:
            self._client = redis_lib.from_url(self._url, decode_responses=True)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, stream: str, event: dict[str, Any]) -> Optional[str]:
        """Returns the XADD message id, or None if Redis is unreachable.
        Callers should treat None as a soft failure and fall back to REST.
        """
        try:
            client = await self.client()
            msg_id = await client.xadd(stream, _flatten(event))
            return msg_id
        except Exception as exc:  # noqa: BLE001 — broad on purpose
            logger.warning(
                "event_bus_publish_failed",
                stream=stream,
                event_type=event.get("type"),
                error=str(exc),
            )
            return None

    async def ensure_consumer_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it doesn't exist. Idempotent."""
        client = await self.client()
        try:
            await client.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("event_bus_group_created", stream=stream, group=group)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "busygroup" in msg or "already exists" in msg:
                return
            raise

    async def read_group(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Returns [(message_id, decoded_payload), ...]. Empty on timeout."""
        client = await self.client()
        try:
            result = await client.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=count,
                block=block_ms,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event_bus_read_failed",
                stream=stream,
                group=group,
                consumer=consumer,
                error=str(exc),
            )
            return []

        out: list[tuple[str, dict[str, Any]]] = []
        for _stream, msgs in result:
            for msg_id, fields in msgs:
                out.append((msg_id, _unflatten(fields)))
        return out

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        client = await self.client()
        await client.xack(stream, group, message_id)


# Module-level singleton — replaced in tests via dependency injection in main.py.
_default_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus


def reset_event_bus_for_tests() -> None:
    """Allows tests to clear the module-level cache after monkeypatching settings."""
    global _default_bus
    _default_bus = None
