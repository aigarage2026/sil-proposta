"""
Dashboard summary — fan-out target for the Portal's aggregator (v3 §3.6, §4.1).

The Portal's `/api/portal/dashboard/aggregate` calls this on every product
in parallel (timeout 2s), caches the result 60s, and renders one card
per product on the unified dashboard.

Returns metrics scoped to the JWT's tenant_id, never cross-tenant.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.database import get_db
from core.logger import get_logger
from core.permissions import require_product
from models.sil_proposta.proposal import Proposal

settings = get_settings()
logger = get_logger()

router = APIRouter()

_CACHE_TTL_SECONDS = 60
_CACHE_KEY_PREFIX = f"{settings.PRODUCT_SLUG}:dashboard:summary:"


class DashboardCard(BaseModel):
    label: str
    value: str | int | float
    delta: Optional[str] = None  # ex.: "+12% vs mês anterior"
    href: Optional[str] = None  # rota interna do produto


class DashboardSummary(BaseModel):
    product: str
    tenant_id: str
    generated_at: datetime
    cards: list[DashboardCard]
    last_activity_at: Optional[datetime] = None
    alerts: list[str] = []


# ── cache helpers (Redis, fall back to no-cache if unavailable) ────────────


async def _get_cached(tenant_id: str) -> Optional[dict]:
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            raw = await r.get(_CACHE_KEY_PREFIX + tenant_id)
            return json.loads(raw) if raw else None
        finally:
            await r.aclose()
    except Exception as e:  # noqa: BLE001
        logger.warning("dashboard_cache_read_failed", error=str(e))
        return None


async def _set_cached(tenant_id: str, payload: dict) -> None:
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await r.setex(
                _CACHE_KEY_PREFIX + tenant_id,
                _CACHE_TTL_SECONDS,
                json.dumps(payload, default=str),
            )
        finally:
            await r.aclose()
    except Exception as e:  # noqa: BLE001
        logger.warning("dashboard_cache_write_failed", error=str(e))


# ── endpoint ────────────────────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard summary for the Portal aggregator",
)
async def summary(
    claims: dict = Depends(require_product()),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    tenant_id: str = claims["tenant_id"]

    cached = await _get_cached(tenant_id)
    if cached:
        return DashboardSummary(**cached)

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_30d_start = now - timedelta(days=30)

    # Total proposals
    total_q = await db.execute(
        select(func.count(Proposal.id)).where(Proposal.tenant_id == tenant_id)
    )
    total = total_q.scalar() or 0

    # Proposals this month
    month_q = await db.execute(
        select(func.count(Proposal.id)).where(
            Proposal.tenant_id == tenant_id,
            Proposal.created_at >= month_start,
        )
    )
    this_month = month_q.scalar() or 0

    # Last 30d
    last30_q = await db.execute(
        select(func.count(Proposal.id)).where(
            Proposal.tenant_id == tenant_id,
            Proposal.created_at >= last_30d_start,
        )
    )
    last_30d = last30_q.scalar() or 0

    # Win rate (proposals with status=won / proposals decided)
    decided_q = await db.execute(
        select(
            func.count(Proposal.id).filter(Proposal.status.in_(["won", "lost"])).label("decided"),
            func.count(Proposal.id).filter(Proposal.status == "won").label("won"),
        ).where(Proposal.tenant_id == tenant_id)
    )
    decided_row = decided_q.one()
    decided = decided_row.decided or 0
    won = decided_row.won or 0
    win_rate = (won / decided * 100) if decided else 0.0

    # Last activity (most recent updated_at among proposals)
    last_activity_q = await db.execute(
        select(func.max(Proposal.updated_at)).where(Proposal.tenant_id == tenant_id)
    )
    last_activity = last_activity_q.scalar()

    cards = [
        DashboardCard(label="Propostas (total)", value=total),
        DashboardCard(
            label="Este mês",
            value=this_month,
            href="/proposals",
        ),
        DashboardCard(label="Últimos 30 dias", value=last_30d),
        DashboardCard(label="Win rate", value=f"{win_rate:.1f}%"),
    ]

    payload = DashboardSummary(
        product=settings.PRODUCT_SLUG,
        tenant_id=tenant_id,
        generated_at=now,
        cards=cards,
        last_activity_at=last_activity,
        alerts=[],
    )

    await _set_cached(tenant_id, payload.model_dump())
    return payload
