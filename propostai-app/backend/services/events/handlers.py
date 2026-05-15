"""
Handlers for events consumed from `portal.events` (v3 §4.2).

All handlers are idempotent — at-least-once delivery means the same
message can be redelivered. Idempotency keys:
  - `tenant.created` → tenant_id (skip if exists)
  - `tenant.suspended` → idempotent by setting is_active=False (already False is fine)
  - `tenant.deleted` → marks suspended + suspension_reason, schedule field
  - `subscription.upgraded/downgraded` → set limits to declared values (last-write-wins)
  - `user.role_changed` → set role to declared value (last-write-wins)

Each handler returns True on success (caller should XACK) and False on
recoverable failure (caller should NOT ack — Redis Streams will redeliver).
Unrecoverable failures (malformed payload, etc.) log and return True to
avoid poison messages blocking the queue.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import get_logger
from core.subscription_middleware import invalidate_tenant_state_cache
from models.tenant import Tenant
from models.user import User

logger = get_logger()


HandlerFn = Callable[[dict[str, Any], AsyncSession], Awaitable[bool]]


# ── tenant.* ────────────────────────────────────────────────────────────────


async def handle_tenant_created(event: dict[str, Any], db: AsyncSession) -> bool:
    """Idempotent local tenant creation. Skips if already present.

    Only fills the minimum the product needs — the canonical record lives
    on the Portal. Provisioning via HMAC remains the primary path; this
    handler is the async alternative (v3 §4.2).
    """
    tenant_id = event.get("tenant_id")
    if not tenant_id:
        logger.warning("event_tenant_created_missing_id", payload=event)
        return True

    existing = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if existing.scalar_one_or_none():
        return True

    tenant = Tenant(
        id=tenant_id,
        name=event.get("name") or tenant_id,
        slug=event.get("slug") or tenant_id,
        plan_slug=event.get("plan_slug") or "trial",
        is_active=True,
    )
    db.add(tenant)
    await db.commit()
    logger.info("event_tenant_created_applied", tenant_id=tenant_id)
    return True


async def handle_tenant_suspended(event: dict[str, Any], db: AsyncSession) -> bool:
    tenant_id = event.get("tenant_id")
    if not tenant_id:
        return True
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        logger.warning("event_tenant_suspended_unknown_tenant", tenant_id=tenant_id)
        return True
    tenant.is_active = False
    tenant.suspended_at = datetime.utcnow()
    tenant.suspension_reason = event.get("reason") or "Suspended by Portal"
    await db.commit()
    invalidate_tenant_state_cache(tenant_id)
    logger.info("event_tenant_suspended_applied", tenant_id=tenant_id)
    return True


async def handle_tenant_deleted(event: dict[str, Any], db: AsyncSession) -> bool:
    """Soft delete: mark suspended with a 'deleted' reason. Hard delete is
    coordinated separately via the LGPD endpoint (v3 §16.5) — the Portal
    triggers that explicitly when the grace period ends.
    """
    tenant_id = event.get("tenant_id")
    if not tenant_id:
        return True
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return True
    tenant.is_active = False
    tenant.suspended_at = datetime.utcnow()
    tenant.suspension_reason = "tenant.deleted"
    await db.commit()
    invalidate_tenant_state_cache(tenant_id)
    logger.info("event_tenant_deleted_applied", tenant_id=tenant_id)
    return True


# ── subscription.* ──────────────────────────────────────────────────────────


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _apply_subscription_change(event: dict[str, Any], db: AsyncSession) -> bool:
    """Common path for upgrade/downgrade — set plan_slug and limits.

    The Portal sends the authoritative target state. We last-write-wins.
    """
    tenant_id = event.get("tenant_id")
    if not tenant_id:
        return True
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        logger.warning("event_subscription_unknown_tenant", tenant_id=tenant_id)
        return True

    plan_slug = event.get("plan_slug")
    if plan_slug:
        tenant.plan_slug = plan_slug

    max_users = _coerce_int(event.get("max_users"))
    if max_users is not None:
        tenant.max_users = max_users

    max_proposals = _coerce_int(event.get("max_proposals_per_month"))
    if max_proposals is not None:
        tenant.max_proposals_per_month = max_proposals

    features = event.get("features")
    if isinstance(features, dict):
        tenant.features = features

    await db.commit()
    invalidate_tenant_state_cache(tenant_id)
    logger.info(
        "event_subscription_applied",
        tenant_id=tenant_id,
        plan_slug=tenant.plan_slug,
        max_users=tenant.max_users,
        max_proposals_per_month=tenant.max_proposals_per_month,
    )
    return True


async def handle_subscription_upgraded(event: dict[str, Any], db: AsyncSession) -> bool:
    return await _apply_subscription_change(event, db)


async def handle_subscription_downgraded(event: dict[str, Any], db: AsyncSession) -> bool:
    return await _apply_subscription_change(event, db)


async def handle_subscription_canceled(event: dict[str, Any], db: AsyncSession) -> bool:
    """Cancel: mark suspension at the effective date. Hard deprovision in
    D+30 is the Portal's responsibility — it will fire either another
    event or call /deprovision when the grace period ends.
    """
    tenant_id = event.get("tenant_id")
    if not tenant_id:
        return True
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return True
    tenant.is_active = False
    tenant.suspended_at = datetime.utcnow()
    tenant.suspension_reason = event.get("reason") or "subscription.canceled"
    await db.commit()
    invalidate_tenant_state_cache(tenant_id)
    logger.info("event_subscription_canceled_applied", tenant_id=tenant_id)
    return True


# ── user.* ──────────────────────────────────────────────────────────────────


async def handle_user_role_changed(event: dict[str, Any], db: AsyncSession) -> bool:
    """Update local user role. Skips silently if the user doesn't exist
    locally — we use lazy creation, the user will be created on next login.
    """
    user_id = event.get("user_id")
    new_role = event.get("role")
    if not user_id or not new_role:
        return True
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return True
    if user.role == new_role:
        return True
    user.role = new_role
    await db.commit()
    logger.info("event_user_role_changed_applied", user_id=user_id, role=new_role)
    return True


# ── registry ────────────────────────────────────────────────────────────────


HANDLERS: dict[str, HandlerFn] = {
    "tenant.created": handle_tenant_created,
    "tenant.suspended": handle_tenant_suspended,
    "tenant.deleted": handle_tenant_deleted,
    "subscription.upgraded": handle_subscription_upgraded,
    "subscription.downgraded": handle_subscription_downgraded,
    "subscription.canceled": handle_subscription_canceled,
    "user.role_changed": handle_user_role_changed,
}


async def dispatch(event: dict[str, Any], db: AsyncSession) -> bool:
    """Look up and invoke a handler. Unknown types are no-ops (return True
    so the message is acked — adding handlers later doesn't require
    backfilling old messages).
    """
    event_type = event.get("type")
    if not event_type:
        logger.warning("event_dispatch_no_type", payload=event)
        return True
    handler = HANDLERS.get(event_type)
    if not handler:
        logger.debug("event_dispatch_unknown_type", type=event_type)
        return True
    try:
        return await handler(event, db)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "event_handler_crashed",
            type=event_type,
            tenant_id=event.get("tenant_id"),
            error=str(exc),
        )
        return False
