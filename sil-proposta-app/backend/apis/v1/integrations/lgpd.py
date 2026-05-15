"""
LGPD endpoints — delete-tenant / export-tenant (v3 §16.5).

Called by the Portal when a tenant exercises:
  - Right to delete (art. 18, VI da LGPD) → POST /lgpd/delete-tenant
  - Right to export (art. 18, II/V da LGPD) → POST /lgpd/export-tenant

Both endpoints are HMAC-protected (NOT user-facing). The Portal coordinates
the request and is responsible for collecting the response from every
product the tenant is provisioned in.

Delete is a hard delete: cascade through SQLAlchemy relationships removes
proposals, companies, users, audit_logs. The tenant row itself is removed.
A summary of what was deleted is returned so the Portal can log the
operation for compliance.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logger import get_logger
from core.portal_hmac import require_portal_hmac
from models.audit_log import AuditLog
from models.company import Company
from models.sil_proposta.proposal import Proposal
from models.tenant import Tenant
from models.user import User

logger = get_logger()

router = APIRouter()


# ── schemas ─────────────────────────────────────────────────────────────────


class LgpdDeleteRequest(BaseModel):
    tenant_id: str
    requested_by: Optional[str] = None
    reason: Optional[str] = None


class LgpdDeleteCounts(BaseModel):
    users: int
    companies: int
    proposals: int
    audit_logs: int


class LgpdDeleteResponse(BaseModel):
    tenant_id: str
    status: Literal["deleted", "not_found"]
    deleted_at: Optional[datetime] = None
    counts: Optional[LgpdDeleteCounts] = None


class LgpdExportRequest(BaseModel):
    tenant_id: str
    requested_by: Optional[str] = None


class LgpdExportResponse(BaseModel):
    tenant_id: str
    status: Literal["exported", "not_found"]
    exported_at: Optional[datetime] = None
    payload: Optional[dict] = None


# ── helpers ─────────────────────────────────────────────────────────────────


async def _count(db: AsyncSession, model, tenant_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    )
    return int(result.scalar_one() or 0)


def _row_to_dict(row) -> dict:
    """Serialize a SQLAlchemy row to a JSON-safe dict.
    datetimes → isoformat, Decimal → float, the rest goes through.
    """
    from decimal import Decimal

    out = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        if isinstance(val, datetime):
            out[col.name] = val.isoformat()
        elif isinstance(val, Decimal):
            out[col.name] = float(val)
        else:
            out[col.name] = val
    return out


# ── endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/delete-tenant",
    response_model=LgpdDeleteResponse,
    dependencies=[Depends(require_portal_hmac)],
    summary="LGPD right-to-delete: hard delete all tenant data",
)
async def delete_tenant(
    body: LgpdDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> LgpdDeleteResponse:
    tenant_q = await db.execute(select(Tenant).where(Tenant.id == body.tenant_id))
    tenant = tenant_q.scalar_one_or_none()
    if not tenant:
        return LgpdDeleteResponse(tenant_id=body.tenant_id, status="not_found")

    counts = LgpdDeleteCounts(
        users=await _count(db, User, body.tenant_id),
        companies=await _count(db, Company, body.tenant_id),
        proposals=await _count(db, Proposal, body.tenant_id),
        audit_logs=await _count(db, AuditLog, body.tenant_id),
    )

    await db.delete(tenant)
    await db.commit()

    logger.info(
        "lgpd_tenant_deleted",
        tenant_id=body.tenant_id,
        requested_by=body.requested_by,
        reason=body.reason,
        counts=counts.model_dump(),
    )

    return LgpdDeleteResponse(
        tenant_id=body.tenant_id,
        status="deleted",
        deleted_at=datetime.utcnow(),
        counts=counts,
    )


@router.post(
    "/export-tenant",
    response_model=LgpdExportResponse,
    dependencies=[Depends(require_portal_hmac)],
    summary="LGPD right-to-export: dump all tenant data as JSON",
)
async def export_tenant(
    body: LgpdExportRequest,
    db: AsyncSession = Depends(get_db),
) -> LgpdExportResponse:
    tenant_q = await db.execute(select(Tenant).where(Tenant.id == body.tenant_id))
    tenant = tenant_q.scalar_one_or_none()
    if not tenant:
        return LgpdExportResponse(tenant_id=body.tenant_id, status="not_found")

    users_q = await db.execute(select(User).where(User.tenant_id == body.tenant_id))
    companies_q = await db.execute(select(Company).where(Company.tenant_id == body.tenant_id))
    proposals_q = await db.execute(select(Proposal).where(Proposal.tenant_id == body.tenant_id))
    audit_q = await db.execute(select(AuditLog).where(AuditLog.tenant_id == body.tenant_id))

    payload = {
        "tenant": _row_to_dict(tenant),
        "users": [_row_to_dict(u) for u in users_q.scalars().all()],
        "companies": [_row_to_dict(c) for c in companies_q.scalars().all()],
        "proposals": [_row_to_dict(p) for p in proposals_q.scalars().all()],
        "audit_logs": [_row_to_dict(a) for a in audit_q.scalars().all()],
    }

    # Strip password hashes — not part of a legitimate LGPD export.
    for u in payload["users"]:
        u.pop("password_hash", None)

    logger.info(
        "lgpd_tenant_exported",
        tenant_id=body.tenant_id,
        requested_by=body.requested_by,
        users=len(payload["users"]),
        companies=len(payload["companies"]),
        proposals=len(payload["proposals"]),
        audit_logs=len(payload["audit_logs"]),
    )

    return LgpdExportResponse(
        tenant_id=body.tenant_id,
        status="exported",
        exported_at=datetime.utcnow(),
        payload=payload,
    )
