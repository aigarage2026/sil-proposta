"""
Servico de geracao de propostas (PS — Proposta de Solução).
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
from models.propostai.proposal_deliverable import ProposalDeliverable
from models.propostai.proposal_legislation import ProposalLegislation
from models.propostai.proposal_premise import ProposalPremise
from models.propostai.proposal_ps import ProposalPS
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
        title=result["ps"]["titulo"],
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
        needs_cpi=result["ps"].get("plano", {}).get("needs_cpi", False),
        total_hours=result["total_hours"],
        valor=result["ps"].get("comercial", {}).get("valor_referencia", 0),
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
    for i, e in enumerate(result["ps"].get("entregaveis", [])):
        db.add(ProposalDeliverable(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            module=e.get("mod", ""),
            item=e.get("item", ""),
            sort_order=i,
        ))

    # Premises
    for i, p in enumerate(result["ps"].get("premissas", [])):
        db.add(ProposalPremise(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            text=p,
            is_standard=i < 8,
            sort_order=i,
        ))

    # Legislation
    for leg in result["ps"].get("fiscal", {}).get("legislacao", []):
        db.add(ProposalLegislation(
            tenant_id=tenant_id,
            proposal_id=proposal.id,
            code=leg if isinstance(leg, str) else leg.get("code", ""),
            description=leg.get("description", "") if isinstance(leg, dict) else "",
        ))

    # PS JSON
    db.add(ProposalPS(
        tenant_id=tenant_id,
        proposal_id=proposal.id,
        ps_json=result["ps"],
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
        "ps": result["ps"],
        "wp_resources": result.get("wp_resources", []),
        "confidence": result.get("confidence", {}),
    }


async def _generate_with_agents(
    db: AsyncSession, payload: IntakePayload, tenant_id: str
) -> dict:
    """Gera via OrchestratorV5 (catalog + LLM descriptive).

    Loads the Tenant so the orchestrator can read its lgpd_anonymize_llm
    and rag_enabled feature flags before each external call. RAGService
    is always constructed (cheap, no HTTP until search()) and gated
    per-tenant inside the orchestrator.
    """
    from services.propostai.agents.orchestrator_v5 import OrchestratorV5
    from services.rag.service import RAGService

    tenant_row = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_row.scalar_one_or_none()

    orch = OrchestratorV5(payload=payload, tenant=tenant, rag=RAGService.from_settings())
    return await orch.run()


def _generate_demo(payload: IntakePayload) -> dict:
    """Fallback: geracao deterministica sem LLM."""
    from services.propostai.demo_generation_service import gerar_proposta_demo
    return gerar_proposta_demo(payload)


async def index_approved_ps_into_socrates(db: AsyncSession, proposal_id: str) -> int:
    """Continuous-improvement hook: rola uma PS aprovada pelo pipeline de
    ingestão e indexa o conteúdo anonimizado no corpus do Sócrates.

    Chamado pelo endpoint PATCH /proposals/{id}/status quando o status
    vira "approved" ou "won". Fail-open: erros são logados pelo caller,
    nunca raise.

    Pipeline aplicado:
      1. Lê ps_json da ProposalPS (texto estruturado da PS gerada).
      2. Serializa em texto plano (uma seção por linha-bloco).
      3. Passa pelo IngestPipeline (anonimização + dedupe + index).

    Retorna o número de chunks indexados (0 se PS vazia / duplicata).
    """
    from sqlalchemy.orm import selectinload

    from models.propostai.proposal import Proposal
    from services.ingest.pipeline import IngestPipeline
    from services.rag.service import RAGService

    row = await db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id)
        .options(selectinload(Proposal.ps))
    )
    proposal = row.scalar_one_or_none()
    if not proposal or not proposal.ps or not proposal.ps.ps_json:
        return 0

    text = _flatten_ps_for_corpus(proposal.ps.ps_json)
    if not text.strip():
        return 0

    pipeline = IngestPipeline(rag=RAGService.from_settings(), llm_reviewer=None)
    # Reuse the pipeline's anonymize+chunk+upsert path, but skip the file
    # loader by writing the text to a synthetic Path. The pipeline's
    # extract_metadata reads year from filename mtime — for a freshly
    # approved PS we just pass a stable name.
    from pathlib import Path
    synthetic = Path(f"/tmp/socrates_approved_{proposal_id}.txt")
    synthetic.write_text(text, encoding="utf-8")
    try:
        # The pipeline expects loader to read the file; a quick override.
        from services.ingest import pipeline as _pl
        original_loader = _pl.load_document
        _pl.load_document = lambda p: text  # type: ignore[assignment]
        try:
            result = await pipeline.process(synthetic)
        finally:
            _pl.load_document = original_loader  # type: ignore[assignment]
    finally:
        synthetic.unlink(missing_ok=True)

    return result.chunks_indexed if result.success else 0


def _flatten_ps_for_corpus(ps_json: dict) -> str:
    """Serializa as seções textuais da PS num bloco que o embedder
    consegue digerir. Ignora campos numéricos puros — só interessa o
    conteúdo descritivo pro Sócrates.
    """
    parts: list[str] = []
    title = ps_json.get("titulo")
    if title:
        parts.append(f"# {title}")
    for key in ("necessidade", "processo_atual", "processo_futuro", "beneficio_esperado"):
        v = ps_json.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(f"## {key}\n{v}")
    entregaveis = ps_json.get("entregaveis") or []
    if entregaveis:
        items = []
        for e in entregaveis:
            if isinstance(e, dict):
                items.append(f"- [{e.get('mod','?')}] {e.get('item','')}")
            elif isinstance(e, str):
                items.append(f"- {e}")
        if items:
            parts.append("## entregaveis\n" + "\n".join(items))
    premissas = ps_json.get("premissas") or []
    if premissas:
        parts.append("## premissas\n" + "\n".join(f"- {p}" for p in premissas))
    return "\n\n".join(parts)
