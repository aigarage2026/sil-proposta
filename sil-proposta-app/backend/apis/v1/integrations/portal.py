"""
Portal-facing endpoints — provision/deprovision (v3 §4.1).

Called by the Control Plane (Portal) when a tenant activates or
deactivates this product. NOT exposed to end users — guarded by HMAC.

Idempotent by design: re-provisioning an existing tenant returns
{status: "exists"}, so the Portal can safely retry.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logger import get_logger
from core.portal_hmac import require_portal_hmac
from core.security import hash_password
from models.company import Company
from models.tenant import Tenant
from models.user import User
from services.events.handlers import dispatch as dispatch_event

logger = get_logger()

router = APIRouter()


# ── schemas ─────────────────────────────────────────────────────────────────


class BrandingPayload(BaseModel):
    primary_color: Optional[str] = None
    logo_url: Optional[str] = None
    extras: Optional[dict] = None


class ProvisionRequest(BaseModel):
    """Body sent by Portal when activating sil-proposta for a tenant."""
    tenant_id: str
    slug: str
    name: str
    plan_slug: str = "trial"
    owner_email: str
    owner_full_name: str
    owner_initial_password: Optional[str] = None
    max_users: Optional[int] = None
    max_proposals_per_month: Optional[int] = None
    branding: Optional[BrandingPayload] = None
    default_company_name: Optional[str] = None


class ProvisionResponse(BaseModel):
    tenant_id: str
    status: Literal["provisioned", "exists", "reactivated"]
    owner_user_id: str
    default_company_id: str


class DeprovisionRequest(BaseModel):
    tenant_id: str
    mode: Literal["soft", "hard"] = "soft"
    reason: Optional[str] = None


class DeprovisionResponse(BaseModel):
    tenant_id: str
    status: Literal["suspended", "deleted", "not_found"]


# ── endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/provision",
    response_model=ProvisionResponse,
    dependencies=[Depends(require_portal_hmac)],
    summary="Provision a tenant for sil-proposta (called by Portal)",
)
async def provision(
    body: ProvisionRequest,
    db: AsyncSession = Depends(get_db),
) -> ProvisionResponse:
    # Idempotent: if tenant already exists, just return its current state.
    existing = await db.execute(select(Tenant).where(Tenant.id == body.tenant_id))
    tenant = existing.scalar_one_or_none()

    if tenant:
        # Reactivate if previously suspended.
        was_suspended = not tenant.is_active
        if was_suspended:
            tenant.is_active = True
            tenant.suspended_at = None
            tenant.suspension_reason = None

        owner_q = await db.execute(
            select(User).where(User.tenant_id == tenant.id, User.role == "owner").limit(1)
        )
        owner = owner_q.scalar_one_or_none()
        company_q = await db.execute(
            select(Company).where(Company.tenant_id == tenant.id, Company.is_default.is_(True)).limit(1)
        )
        company = company_q.scalar_one_or_none()

        if not owner or not company:
            # Inconsistent state — fall through to recreate the missing pieces.
            logger.warning(
                "provision_inconsistent_state",
                tenant_id=tenant.id,
                missing_owner=owner is None,
                missing_company=company is None,
            )
        else:
            await db.commit()
            return ProvisionResponse(
                tenant_id=tenant.id,
                status="reactivated" if was_suspended else "exists",
                owner_user_id=owner.id,
                default_company_id=company.id,
            )

    # Fresh provision.
    if not tenant:
        tenant = Tenant(
            id=body.tenant_id,
            name=body.name,
            slug=body.slug,
            plan_slug=body.plan_slug,
            max_users=body.max_users or 5,
            max_proposals_per_month=body.max_proposals_per_month or 50,
            primary_color=(body.branding.primary_color if body.branding else None) or "#3B7BF8",
            logo_url=body.branding.logo_url if body.branding else None,
            branding=body.branding.model_dump(exclude_none=True) if body.branding else {},
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

    company_q = await db.execute(
        select(Company).where(Company.tenant_id == tenant.id, Company.is_default.is_(True)).limit(1)
    )
    company = company_q.scalar_one_or_none()
    if not company:
        company = Company(
            tenant_id=tenant.id,
            name=body.default_company_name or body.name,
            is_default=True,
        )
        db.add(company)
        await db.flush()

    owner_q = await db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == body.owner_email).limit(1)
    )
    owner = owner_q.scalar_one_or_none()
    if not owner:
        owner = User(
            tenant_id=tenant.id,
            email=body.owner_email,
            full_name=body.owner_full_name,
            password_hash=hash_password(body.owner_initial_password)
            if body.owner_initial_password
            else None,
            role="owner",
            is_active=True,
            is_email_verified=True,
        )
        db.add(owner)
        await db.flush()

    await db.commit()
    logger.info(
        "tenant_provisioned",
        tenant_id=tenant.id,
        slug=tenant.slug,
        plan=tenant.plan_slug,
        owner_email=body.owner_email,
    )
    return ProvisionResponse(
        tenant_id=tenant.id,
        status="provisioned",
        owner_user_id=owner.id,
        default_company_id=company.id,
    )


@router.post(
    "/deprovision",
    response_model=DeprovisionResponse,
    dependencies=[Depends(require_portal_hmac)],
    summary="Deprovision a tenant (soft suspend or hard delete)",
)
async def deprovision(
    body: DeprovisionRequest,
    db: AsyncSession = Depends(get_db),
) -> DeprovisionResponse:
    tenant_q = await db.execute(select(Tenant).where(Tenant.id == body.tenant_id))
    tenant = tenant_q.scalar_one_or_none()
    if not tenant:
        return DeprovisionResponse(tenant_id=body.tenant_id, status="not_found")

    if body.mode == "soft":
        tenant.is_active = False
        tenant.suspended_at = datetime.utcnow()
        tenant.suspension_reason = body.reason or "Deprovisioned by Portal"
        await db.commit()
        logger.info("tenant_suspended", tenant_id=tenant.id, reason=tenant.suspension_reason)
        return DeprovisionResponse(tenant_id=tenant.id, status="suspended")

    # mode == "hard": cascade delete via SQLAlchemy relationships
    await db.delete(tenant)
    await db.commit()
    logger.info("tenant_hard_deleted", tenant_id=body.tenant_id)
    return DeprovisionResponse(tenant_id=body.tenant_id, status="deleted")


# ── REST fallback for portal.events (v3 §21.2.3) ────────────────────────────


class SyncTenantRequest(BaseModel):
    """A single Portal event delivered via REST instead of Redis Streams.
    Used while B4 (portal.events stream) is 🔴 unavailable on the Portal.
    Payload mirrors what XADD would carry: a `type` plus event-specific keys.
    """
    type: str
    tenant_id: Optional[str] = None
    payload: Optional[dict] = None


class SyncTenantResponse(BaseModel):
    status: Literal["applied", "skipped", "deferred"]
    type: str


@router.post(
    "/sync-tenant",
    response_model=SyncTenantResponse,
    dependencies=[Depends(require_portal_hmac)],
    summary="REST fallback for portal.events (used while Redis Streams is unavailable)",
)
async def sync_tenant(
    body: SyncTenantRequest,
    db: AsyncSession = Depends(get_db),
) -> SyncTenantResponse:
    event = {"type": body.type}
    if body.tenant_id:
        event["tenant_id"] = body.tenant_id
    if body.payload:
        # Merge payload at top level — handlers expect a flat dict.
        event.update(body.payload)

    ok = await dispatch_event(event, db)
    if not ok:
        # Handler returned False — caller should retry. We surface 503 so
        # the Portal can apply its own backoff/retry policy.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to apply event {body.type}; retry later",
        )
    return SyncTenantResponse(status="applied", type=body.type)
