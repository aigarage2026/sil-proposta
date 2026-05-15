"""
Servico de geracao de propostas.
Orquestra agentes IA (OrchestratorV5) e fallback para demo mode.

OrchestratorV5 é o catálogo-first migrado em §Onda 5: classifica a
demanda deterministicamente, chama LLMs só para texto descritivo, e
honra a flag LGPD do tenant antes de mandar a RFP para a API externa.
"""
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.logger import get_logger
from models.propostai.agent_execution import AgentExecution
from models.propostai.proposal import Proposal
from models.propostai.proposal_dam import ProposalDam
from models.propostai.proposal_deliverable import ProposalDeliverable
from models.propostai.proposal_legislation import ProposalLegislation
from models.propostai.proposal_premise import ProposalPremise
from models.propostai.proposal_resource import ProposalResource
from models.tenant import Tenant
from schemas.intake import IntakePayload

settings = get_settings()
logger = get_logger()


async def generate_proposal(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    payload: IntakePayload,
) -> dict:
    """Gera proposta via agentes IA ou demo mode."""
    start = time.monotonic()

    # Try the LLM orchestrator when at least one provider key is set AND
    # demo mode is off. Either OpenAI or Anthropic is enough — OrchestratorV5
    # routes per-agent and falls back gracefully when one provider fails.
    has_llm = bool(settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY)
    if has_llm and not settings.SAP_DEMO_MODE_ENABLED:
        try:
            result = await _generate_with_agents(db, payload, tenant_id)
            mode = "llm"
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_generation_failed_falling_back_to_demo", error=str(e))
            result = _generate_demo(payload)
            mode = "demo"
    else:
        result = _generate_demo(payload)
        mode = "demo"

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Persistir proposta
    proposal = Proposal(
        tenant_id=tenant_id,
        company_id=payload.company_id,
        created_by=user_id,
        title=result["dam"]["titulo"],
        project_type=payload.project_type,
        sap_version=payload.sap_version,
        states=payload.states,
        commercial_model=payload.commercial_model,
        rfp_text=payload.rfp_text,
        new_law=payload.new_law,
        hours_presale=payload.hours_presale,
        notes=payload.notes,
        lang=payload.lang,
        status="draft",
        main_proc=result.get("main_proc", "SD"),
        needs_cpi=result["dam"].get("plano", {}).get("needs_cpi", False),
        total_hours=result["total_hours"],
        valor=result["dam"].get("comercial", {}).get("valor_referencia", 0),
        confidence_escopo=result.get("confidence", {}).get("escopo", 0),
        confidence_horas=result.get("confidence", {}).get("horas", 0),
        confidence_legislacao=result.get("confidence", {}).get("legislacao", 0),
        confidence_comercial=result.get("confidence", {}).get("comercial", 0),
        generation_mode=mode,
        agents_fired=result.get("agents_fired", []),
        generation_time_ms=elapsed_ms,
    )
    db.add(proposal)
    await db.flush()

    # Resources (WP)
    for r in result.get("wp_resources", []):
        db.add(ProposalResource(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            frente=r["frente"],
            nivel=r.get("nivel", "Senior"),
            dias=r["dias"],
            horas=r["dias"] * 8,
            cost_rate=settings.SAP_DEFAULT_TARIFF_PER_HOUR,
        ))

    # Deliverables
    for i, e in enumerate(result["dam"].get("entregaveis", [])):
        db.add(ProposalDeliverable(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            module=e.get("mod", ""),
            item=e.get("item", ""),
            sort_order=i,
        ))

    # Premises
    for i, p in enumerate(result["dam"].get("premissas", [])):
        db.add(ProposalPremise(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            text=p,
            is_standard=i < 8,
            sort_order=i,
        ))

    # Legislation
    for leg in result["dam"].get("fiscal", {}).get("legislacao", []):
        db.add(ProposalLegislation(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            code=leg if isinstance(leg, str) else leg.get("code", ""),
            description=leg.get("description", "") if isinstance(leg, dict) else "",
        ))

    # DAM JSON
    db.add(ProposalDam(
        tenant_id=tenant_id,
        proposal_id=proposal.id,
        dam_json=result["dam"],
    ))

    # Agent executions
    for agent_name in result.get("agents_fired", []):
        db.add(AgentExecution(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            agent_name=agent_name,
            status="done",
            duration_ms=elapsed_ms // max(len(result.get("agents_fired", [])), 1),
        ))

    return {
        "proposal_id": proposal.id,
        "title": proposal.title,
        "status": "draft",
        "generation_mode": mode,
        "generation_time_ms": elapsed_ms,
        "total_hours": result["total_hours"],
        "main_proc": result.get("main_proc"),
        "agents_fired": result.get("agents_fired", []),
        "dam": result["dam"],
        "wp_resources": result.get("wp_resources", []),
        "confidence": result.get("confidence", {}),
    }


async def _generate_with_agents(
    db: AsyncSession, payload: IntakePayload, tenant_id: str
) -> dict:
    """Gera via OrchestratorV5 (catalog + LLM descriptive).

    Loads the Tenant so the orchestrator can read its lgpd_anonymize_llm
    feature flag before anonymizing the RFP for external LLM calls.
    """
    from services.propostai.agents.orchestrator_v5 import OrchestratorV5

    tenant_row = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_row.scalar_one_or_none()

    orch = OrchestratorV5(payload=payload, tenant=tenant)
    return await orch.run()


def _generate_demo(payload: IntakePayload) -> dict:
    """Fallback: geracao deterministica sem LLM."""
    from services.propostai.demo_generation_service import gerar_proposta_demo
    return gerar_proposta_demo(payload)
