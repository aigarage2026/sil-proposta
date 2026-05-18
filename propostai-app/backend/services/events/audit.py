"""
Audit helper — extracts request context and emits audit.action events
(v3 §4.3, §15.4).

Wraps services.events.publisher.emit_audit_action() so call sites in route
handlers don't have to repeat the boilerplate of pulling trace_id / IP /
user fields out of FastAPI's Request and User objects.

Errors are swallowed: telemetry must never fail a business operation.
The underlying publisher already logs failures via structlog.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Request

from core.logger import get_logger
from models.user import User
from services.events.publisher import emit_audit_action

logger = get_logger()


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    # X-Forwarded-For wins behind the gateway, fall back to client.host.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _trace_id(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    return getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-ID")


async def audit(
    request: Optional[Request],
    user: User,
    action: str,
    entity: str,
    entity_id: Optional[str] = None,
    changes: Optional[dict[str, Any]] = None,
) -> str:
    """Emit one audit.action event; return the delivery channel:
    "stream", "rest", or "dropped". Never raises — logs on failure.
    """
    try:
        return await emit_audit_action(
            tenant_id=user.tenant_id,
            user_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            changes=changes,
            ip_address=_client_ip(request),
            trace_id=_trace_id(request),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "audit_helper_failed",
            action=action,
            entity=entity,
            entity_id=entity_id,
            error=str(exc),
        )
        return "dropped"
