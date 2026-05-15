"""
API v1 — Proposals CRUD + Generation + Export.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.security import get_current_user
from models.sil_proposta.proposal import Proposal
from models.user import User
from schemas.intake import IntakePayload
from schemas.proposal import (
    AgentExecutionSchema,
    ConfidenceSchema,
    DeliverableSchema,
    LegislationSchema,
    PremiseSchema,
    ProposalDetail,
    ProposalListResponse,
    ProposalStatusUpdate,
    ProposalSummary,
    ResourceSchema,
)
from services.events.audit import audit
from services.events.publisher import emit_usage_metric

router = APIRouter()


@router.get("", response_model=ProposalListResponse)
async def list_proposals(
    company_id: str = None,
    status_filter: str = None,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Listar propostas do tenant."""
    query = select(Proposal).where(Proposal.tenant_id == user.tenant_id)
    if company_id:
        query = query.where(Proposal.company_id == company_id)
    if status_filter:
        query = query.where(Proposal.status == status_filter)
    query = query.order_by(Proposal.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    proposals = result.scalars().all()

    count_q = select(func.count(Proposal.id)).where(Proposal.tenant_id == user.tenant_id)
    total = (await db.execute(count_q)).scalar() or 0

    return ProposalListResponse(
        proposals=[ProposalSummary.model_validate(p) for p in proposals],
        total=total,
    )


@router.get("/{proposal_id}", response_model=ProposalDetail)
async def get_proposal(
    proposal_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detalhe completo de uma proposta."""
    result = await db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id, Proposal.tenant_id == user.tenant_id)
        .options(
            selectinload(Proposal.resources),
            selectinload(Proposal.deliverables),
            selectinload(Proposal.premises),
            selectinload(Proposal.legislations),
            selectinload(Proposal.dam),
            selectinload(Proposal.agent_executions),
        )
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta nao encontrada")

    return ProposalDetail(
        id=proposal.id,
        title=proposal.title,
        status=proposal.status,
        project_type=proposal.project_type,
        sap_version=proposal.sap_version,
        states=proposal.states or [],
        commercial_model=proposal.commercial_model,
        rfp_text=proposal.rfp_text,
        new_law=proposal.new_law,
        hours_presale=proposal.hours_presale or 0,
        notes=proposal.notes,
        lang=proposal.lang or "pt",
        main_proc=proposal.main_proc,
        needs_cpi=proposal.needs_cpi,
        total_hours=proposal.total_hours,
        valor=float(proposal.valor) if proposal.valor else None,
        generation_mode=proposal.generation_mode,
        agents_fired=proposal.agents_fired,
        generation_time_ms=proposal.generation_time_ms,
        confidence=ConfidenceSchema(
            escopo=float(proposal.confidence_escopo or 0),
            horas=float(proposal.confidence_horas or 0),
            legislacao=float(proposal.confidence_legislacao or 0),
            comercial=float(proposal.confidence_comercial or 0),
        ),
        resources=[ResourceSchema.model_validate(r) for r in proposal.resources],
        deliverables=[DeliverableSchema.model_validate(d) for d in proposal.deliverables],
        premises=[PremiseSchema.model_validate(p) for p in proposal.premises],
        legislations=[LegislationSchema.model_validate(leg) for leg in proposal.legislations],
        agent_executions=[AgentExecutionSchema.model_validate(a) for a in proposal.agent_executions],
        dam_json=proposal.dam.dam_json if proposal.dam else None,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_proposal(
    payload: IntakePayload,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Criar proposta e disparar geracao com agentes IA."""
    from services.sil_proposta.generation_service import generate_proposal

    result = await generate_proposal(
        db=db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        payload=payload,
    )

    proposal_id = result.get("id") or result.get("proposal_id") if isinstance(result, dict) else None
    await audit(
        request, user,
        action="proposal.created",
        entity="Proposal",
        entity_id=proposal_id,
        changes={"title": getattr(payload, "title", None)},
    )
    await emit_usage_metric(
        tenant_id=user.tenant_id,
        metric="proposals_generated",
        value=1,
        unit="count",
        metadata={"proposal_id": proposal_id} if proposal_id else None,
    )
    return result


@router.patch("/{proposal_id}/status")
async def update_status(
    proposal_id: str,
    body: ProposalStatusUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atualizar status da proposta."""
    result = await db.execute(
        select(Proposal).where(Proposal.id == proposal_id, Proposal.tenant_id == user.tenant_id)
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta nao encontrada")

    valid_transitions = {
        "draft": ["review", "approved"],
        "review": ["draft", "approved"],
        "approved": ["won", "lost"],
        "won": ["approved"],
        "lost": ["approved"],
    }
    allowed = valid_transitions.get(proposal.status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Transicao invalida: {proposal.status} -> {body.status}. Permitidas: {allowed}",
        )

    old_status = proposal.status
    proposal.status = body.status

    await audit(
        request, user,
        action="proposal.status_changed",
        entity="Proposal",
        entity_id=proposal_id,
        changes={"from": old_status, "to": body.status},
    )
    return {"ok": True, "proposal_id": proposal_id, "status": body.status}


@router.delete("/{proposal_id}")
async def delete_proposal(
    proposal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deletar proposta."""
    result = await db.execute(
        select(Proposal).where(Proposal.id == proposal_id, Proposal.tenant_id == user.tenant_id)
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta nao encontrada")

    title = proposal.title
    await db.delete(proposal)

    await audit(
        request, user,
        action="proposal.deleted",
        entity="Proposal",
        entity_id=proposal_id,
        changes={"title": title},
    )
    return {"ok": True, "proposal_id": proposal_id}


@router.get("/{proposal_id}/export/dam")
async def export_dam(
    proposal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download DAM como Word."""
    from services.sil_proposta.export_service import generate_dam_document

    result = await db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id, Proposal.tenant_id == user.tenant_id)
        .options(
            selectinload(Proposal.resources),
            selectinload(Proposal.deliverables),
            selectinload(Proposal.premises),
            selectinload(Proposal.dam),
        )
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposta nao encontrada")

    buf = generate_dam_document(proposal)
    fname = f"DAM_{proposal.title[:30].replace(' ', '_')}.docx"

    await audit(
        request, user,
        action="proposal.dam_exported",
        entity="Proposal",
        entity_id=proposal_id,
    )
    await emit_usage_metric(
        tenant_id=user.tenant_id,
        metric="dam_documents_exported",
        value=1,
        unit="count",
        metadata={"proposal_id": proposal_id},
    )

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
