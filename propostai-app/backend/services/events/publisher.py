"""
Outbound event publishers (v3 §4.3, §15.4).

Two channels per event class:
  1. Primary: XADD to `{slug}.events` stream (Portal consumes).
  2. Fallback: HTTP POST to Portal REST endpoint, used when Redis is
     unreachable or `EVENT_PUBLISHER_PREFER_REST=true` (the latter is the
     B4 🔴 escape hatch from §1.5 — stream doesn't exist yet, REST does).

Two event kinds matter for Onda 3:
  - `usage.metric` (billing): { tenant_id, metric, value, unit, ts }
  - `audit.action` (audit log): { tenant_id, user_id, action, entity,
    entity_id, changes?, ip?, trace_id? }

The publisher API is fire-and-forget. Callers don't wait for confirmation —
domain operations must not block on telemetry. Failures log + drop.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import httpx

from core.config import get_settings
from core.event_bus import PRODUCT_EVENTS_STREAM, EventBus, get_event_bus
from core.logger import get_logger

logger = get_logger()
settings = get_settings()


PORTAL_USAGE_PATH = "/api/portal/usage/events"
PORTAL_AUDIT_PATH = "/api/portal/audit/events"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


async def _post_to_portal(path: str, payload: dict[str, Any]) -> bool:
    """REST fallback. Best-effort: short timeout, no retries.
    Returns True on 2xx, False otherwise (network, 4xx, 5xx).
    """
    url = f"{settings.PORTAL_API_URL.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json"}
    if settings.PORTAL_API_KEY:
        headers["X-API-Key"] = settings.PORTAL_API_KEY
    try:
        async with httpx.AsyncClient(timeout=3.0) as http:
            response = await http.post(url, json=payload, headers=headers)
        if 200 <= response.status_code < 300:
            return True
        logger.warning(
            "event_rest_fallback_non_2xx",
            path=path,
            status=response.status_code,
            event_type=payload.get("type"),
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "event_rest_fallback_failed",
            path=path,
            event_type=payload.get("type"),
            error=str(exc),
        )
        return False


async def _emit(
    event: dict[str, Any],
    rest_path: str,
    bus: Optional[EventBus] = None,
) -> str:
    """Returns one of: "stream", "rest", "dropped".

    Stream first unless EVENT_PUBLISHER_PREFER_REST is set. REST on stream
    failure. Drop on both failures (event is logged, business continues).
    """
    prefer_rest = getattr(settings, "EVENT_PUBLISHER_PREFER_REST", False)
    bus = bus or get_event_bus()

    if not prefer_rest:
        msg_id = await bus.publish(PRODUCT_EVENTS_STREAM, event)
        if msg_id is not None:
            return "stream"

    if await _post_to_portal(rest_path, event):
        return "rest"

    logger.error("event_dropped", event_type=event.get("type"), payload=event)
    return "dropped"


# ── public API ──────────────────────────────────────────────────────────────


async def emit_usage_metric(
    *,
    tenant_id: str,
    metric: str,
    value: float | int,
    unit: str = "count",
    metadata: Optional[dict[str, Any]] = None,
    bus: Optional[EventBus] = None,
) -> str:
    """Reports usage to the Portal for billing (v3 §4.3 `usage.metric`)."""
    event = {
        "type": "usage.metric",
        "tenant_id": tenant_id,
        "metric": metric,
        "value": value,
        "unit": unit,
        "ts": _now_iso(),
        "product": settings.PRODUCT_SLUG,
    }
    if metadata:
        event["metadata"] = metadata
    return await _emit(event, PORTAL_USAGE_PATH, bus=bus)


async def emit_audit_action(
    *,
    tenant_id: str,
    user_id: str,
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    changes: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    trace_id: Optional[str] = None,
    bus: Optional[EventBus] = None,
) -> str:
    """Publishes an audit entry (v3 §15.4 audit central)."""
    event = {
        "type": "audit.action",
        "tenant_id": tenant_id,
        "user_id": user_id,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "changes": changes,
        "ip_address": ip_address,
        "trace_id": trace_id,
        "ts": _now_iso(),
        "product": settings.PRODUCT_SLUG,
    }
    return await _emit(event, PORTAL_AUDIT_PATH, bus=bus)
