"""
PropostAI — Orquestrador Determinístico v5 (v3 Onda 5).

Catálogo Python decide TUDO; LLM só gera texto descritivo. Each call is
independent — no global state survives between proposals (legacy used a
module-level `_billing_buffer`; here billing lives on the LLMClient
instance and is returned by run()).

Pipeline (preserved from the legacy port):
  1. classify_demand(rfp)            — Python deterministic
  2. build_entregaveis(tipo)         — Python deterministic
       └─ for tipo=="generic" → ask LLM for itens
  3. LLM details in parallel:
       - detalhar_abap (per ABAP item, 1 call each)
       - detalhar_modulo_funcional (one call per functional module)
       - gerar_as_is_to_be (one call total)
  4. calculate_team(tipo, total_horas) — Python deterministic
  5. filter_premissas / EXCLUSOES_PADRAO
  6. comercial = total_horas × tarifa_hora (default 250)
  7. assemble ps {} with the shape the PS Word generator already consumes
  8. qa_review (LLM)
  9. return { main_proc, total_hours, wp_resources, confidence,
              agents_fired, ps, billing_records }

LGPD anonymization (v3 §4.5.5 E2): the orchestrator masks the RFP once,
up front, when the tenant has anonymization enabled. The masked text is
what flows into every LLM prompt. The original RFP is preserved on the
returned ps.necessidade so the DB / PS Word generator render real
values for the customer-facing document.

RAG context (v3 §4.5.5 E5 + Onda 5 close): when a RAGService is injected
AND the tenant opted in via features.rag_enabled, the orchestrator runs
one tenant-scoped vector search at the start of run() using the
anonymized RFP as the query. The top-k chunks are concatenated into a
preamble that's prepended to every descriptive LLM prompt. Failures
during retrieval are swallowed (fail-open) — the catalog path is always
authoritative.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from core.logger import get_logger
from services.lgpd.anonymizer import anonymize, should_anonymize_for_tenant
from services.propostai.agents.catalog import (
    EXCLUSOES_PADRAO,
    PREMISSAS_PADRAO,
    build_entregaveis,
    calculate_team,
    classify_demand,
    filter_entregaveis,
    filter_premissas,
    get_demand_config,
)
from services.propostai.agents.llm_client import LLMClient, parse_llm_json
from services.propostai.agents.profiles import resolve_profile_for_tenant
from services.rag.service import RAGService

logger = get_logger()


SAP_VERSION_LABELS = {
    "ecc604": "ECC ≤ 6.04",
    "ecc605": "ECC 6.05+",
    "s4op": "S/4HANA On-premise",
    "s4cloud": "S/4HANA Cloud",
}

DEFAULT_TARIFA_HORA = 250

FUNCTIONAL_MODULES = ("SD", "FI", "MM", "CO", "PP", "HR", "QM", "WM", "BASIS")

# RAG: how many chunks to pull per proposal. Keep small — we paste these
# verbatim into every agent prompt, so cost scales with k × agents.
RAG_TOP_K = 3
RAG_PURPOSE = "legislacao"


def _rag_enabled_for_tenant(tenant) -> bool:
    """Per-tenant opt-in. Fail-closed (off by default) — most tenants won't
    have an indexed corpus yet, and embedding the RFP costs API calls.
    Mirrors the should_anonymize_for_tenant shape so callers in tests can
    use the same SimpleNamespace(features={...}) idiom.
    """
    if tenant is None:
        return False
    features = getattr(tenant, "features", None) or {}
    return bool(features.get("rag_enabled"))


def _format_rag_preamble(chunks: list[dict]) -> str:
    """Turn search hits into a compact block the LLM can read once and
    reuse across the prompt. Each item: rank, score, text.
    """
    if not chunks:
        return ""
    lines = ["Contexto recuperado da base de conhecimento (use como referência, não copie):"]
    for i, c in enumerate(chunks, 1):
        text = (c.get("payload") or {}).get("text", "") or ""
        if not text:
            continue
        score = c.get("score", 0.0)
        lines.append(f"[{i}] (score={score:.2f}) {text}")
    return "\n".join(lines) + "\n\n"


# ── LLM agents (descriptive text only) ─────────────────────────────────────


@dataclass
class _AgentContext:
    """Bundle of injectables a single LLM agent needs."""
    llm: LLMClient
    rfp_for_llm: str  # already anonymized if the tenant requested it
    rag_preamble: str = ""  # empty when RAG is off or returned nothing


async def _gerar_as_is_to_be(ctx: _AgentContext) -> dict:
    system = (
        "Você é um arquiteto SAP. Analise a RFP e descreva processo atual e futuro. "
        'Retorne APENAS JSON: {"processo_atual":"...","processo_futuro":"...","beneficio":"..."} '
        "Sem markdown."
    )
    try:
        text = await ctx.llm.call(
            system=system,
            user=f"{ctx.rag_preamble}RFP:\n{ctx.rfp_for_llm}",
            agent_name="AS_IS_TO_BE",
        )
        return parse_llm_json(text) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("orchestrator_as_is_to_be_failed", error=str(exc))
        return {}


async def _detalhar_abap_item(ctx: _AgentContext, obj: dict) -> None:
    """Detalha UM objeto ABAP. Mutação in-place (segue padrão do legado)."""
    system = (
        "Você é um arquiteto ABAP sênior SAP da Direto ao Ponto.\n"
        "Para o objeto ABAP recebido, gere passos detalhados (transações SE11/SE38/SE80/SM30/SE19, "
        "nomes Z, BAdIs, parâmetros, validações) e código ABAP real funcional (TYPES/DATA, lógica, "
        "tratamento de erros, comentários).\n"
        "Retorne APENAS JSON (sem markdown):\n"
        '{"como_fazer":"1) ... 2) ...","parametros":"campos e valores","transacoes":["T1"],'
        '"exemplo_codigo":"REPORT z...\\nDATA: ..."}'
    )
    user_msg = (
        f"{ctx.rag_preamble}RFP:\n{ctx.rfp_for_llm}\n\n"
        f"Objeto: {obj.get('item','')}\n"
        f"Tipo: {obj.get('tipo','')}\n"
        f"Transação base: {obj.get('transacao','')}"
    )
    try:
        text = await ctx.llm.call(
            system=system, user=user_msg, agent_name="ABAP", max_tokens=3000,
        )
        d = parse_llm_json(text) or {}
        if d:
            obj["como_fazer"] = d.get("como_fazer", "")
            obj["parametros"] = d.get("parametros", "")
            obj["transacoes"] = d.get("transacoes", [])
            obj["exemplo_codigo"] = d.get("exemplo_codigo", "")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "orchestrator_abap_item_failed",
            item=(obj.get("item", "") or "")[:60],
            error=str(exc),
        )


async def _detalhar_abap(ctx: _AgentContext, abap_objects: list[dict]) -> list[dict]:
    """Detalha cada objeto ABAP em paralelo (1 call por item — evita truncamento)."""
    if not abap_objects:
        return []
    await asyncio.gather(
        *[_detalhar_abap_item(ctx, o) for o in abap_objects],
        return_exceptions=True,
    )
    return abap_objects


async def _detalhar_modulo_funcional(
    ctx: _AgentContext, modulo: str, entregaveis: list[dict],
) -> list[dict]:
    func_items = [e for e in entregaveis if e.get("mod") == modulo]
    if not func_items:
        return entregaveis

    system = (
        f"Você é um arquiteto SAP {modulo} sênior da Direto ao Ponto.\n"
        'Para CADA entregável, gere passo-a-passo detalhado para execução.\n'
        "FORMATO OBRIGATÓRIO para \"como_fazer\":\n"
        '"1) Transação XXXX: ação específica com parâmetros\n'
        ' 2) Configurar em SPRO > caminho > subcaminho\n'
        ' 3) Validar em transação YYYY"\n'
        "Retorne APENAS JSON:\n"
        '{"detalhes":[{"item":"<nome>","como_fazer":"<passos>","parametros":"<campos>",'
        '"transacoes":["T1"]}]}\n'
        "Sem markdown."
    )
    itens_texto = "\n".join(f"- {e.get('item','')}" for e in func_items)
    try:
        text = await ctx.llm.call(
            system=system,
            user=f"{ctx.rag_preamble}RFP:\n{ctx.rfp_for_llm}\n\nEntregáveis {modulo}:\n{itens_texto}",
            agent_name=modulo,
            max_tokens=4000,
        )
        result = parse_llm_json(text) or {}
        detalhes = result.get("detalhes", []) if isinstance(result, dict) else []
        for obj in func_items:
            o_item = (obj.get("item", "") or "").lower()
            for d in detalhes:
                d_item = (d.get("item", "") or "").lower()
                if d_item and (d_item in o_item or o_item in d_item or d_item[:30] in o_item):
                    obj["como_fazer"] = d.get("como_fazer", "")
                    obj["parametros"] = d.get("parametros", "")
                    obj["transacoes"] = d.get("transacoes", [])
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("orchestrator_module_failed", modulo=modulo, error=str(exc))
    return entregaveis


async def _qa_review(ctx: _AgentContext, ps: dict) -> dict:
    """QA revisa a proposta consolidada. Sempre retorna um dict (fail-open)."""
    import json as _json
    system = (
        "Você é um QA sênior de propostas SAP. Verifique se a proposta faz sentido para a RFP.\n"
        "Critérios: (1) entregáveis batem com a RFP, (2) sem contaminação, (3) horas razoáveis.\n"
        'Retorne APENAS JSON: {"aprovado":true,"score":90,"problemas":[],"sugestoes":[]}'
    )
    resumo = _json.dumps(
        {
            "rfp": (ctx.rfp_for_llm or "")[:500],
            "modulos": ps.get("plano", {}).get("modules", []),
            "n_entregaveis": len(ps.get("entregaveis", [])),
            "horas": ps.get("total_horas", 0),
            "valor": ps.get("comercial", {}).get("valor_referencia", 0),
        },
        ensure_ascii=False,
    )
    try:
        text = await ctx.llm.call(
            system=system, user=f"PROPOSTA:\n{resumo}", agent_name="QA",
        )
        return parse_llm_json(text) or {"aprovado": True, "score": 80, "problemas": [], "sugestoes": []}
    except Exception as exc:  # noqa: BLE001
        logger.warning("orchestrator_qa_failed", error=str(exc))
        return {"aprovado": True, "score": 0, "problemas": [], "sugestoes": []}


async def _gerar_entregaveis_genericos(ctx: _AgentContext) -> list[dict]:
    system = (
        "Você é um arquiteto SAP. Analise a RFP e gere entregáveis específicos.\n"
        "Cada entregável DEVE ter: mod (SD/FI/MM/ABAP), item (descrição com transação SAP real), "
        "horas, fase.\n"
        "NÃO use placeholders genéricos como 'Descrição', 'item', 'premissa'.\n"
        'Retorne APENAS JSON: {"entregaveis":[{"mod":"SD","item":"...","horas":16,"fase":"Realize"}]}\n'
        "Sem markdown."
    )
    try:
        text = await ctx.llm.call(
            system=system, user=f"{ctx.rag_preamble}RFP:\n{ctx.rfp_for_llm}", agent_name="GENERIC",
        )
        r = parse_llm_json(text) or {}
        return r.get("entregaveis", []) if isinstance(r, dict) else []
    except Exception as exc:  # noqa: BLE001
        logger.warning("orchestrator_generic_failed", error=str(exc))
        return []


# ── orchestrator class ─────────────────────────────────────────────────────


@dataclass
class OrchestratorV5:
    """Catalog-driven, LLM-light proposal orchestrator.

    Construction:
      OrchestratorV5(payload=<intake>, tenant=<Tenant or None>, llm=<LLMClient or None>)

    `payload` only needs the attributes the legacy used:
      .rfp_text, .states, .sap_version, .project_type, optional .client_name.

    `tenant` is passed to the LGPD anonymizer; None → defaults to "anonymize"
    (fail-closed). Use a stub with `features={"lgpd_anonymize_llm": False}`
    in tests that need the LLM to see real RFP text.

    `llm` is the LLMClient instance — pass a stub in tests; production
    callers can omit it to get one from settings.

    `rag` is an optional RAGService. When set AND the tenant opted in
    (`tenant.features['rag_enabled']`), the orchestrator pulls top-k
    chunks once and uses them as a preamble in every descriptive prompt.
    Production callers pass `RAGService.from_settings()`; tests inject a
    stub. Leave None to disable RAG entirely (the catalog path stands).
    """
    payload: Any
    tenant: Any = None
    llm: LLMClient = field(default_factory=LLMClient.from_settings)
    rag: Optional[RAGService] = None

    async def run(self) -> dict:
        rfp_real = self.payload.rfp_text or ""
        ufs = self.payload.states or []
        client_name = getattr(self.payload, "client_name", "") or "Cliente"

        rfp_for_llm = anonymize(rfp_real) if should_anonymize_for_tenant(self.tenant) else rfp_real

        profile = resolve_profile_for_tenant(self.tenant)

        agents_fired: list[str] = [
            "Classificador (Python determinístico)",
            f"Calibração: perfil '{profile.name}'",
        ]

        rag_preamble = await self._fetch_rag_preamble(rfp_for_llm or "")
        if rag_preamble:
            agents_fired.append(f"RAG (top-{RAG_TOP_K} chunks)")

        ctx = _AgentContext(
            llm=self.llm, rfp_for_llm=rfp_for_llm or "", rag_preamble=rag_preamble,
        )

        # 1. classify
        tipo = classify_demand(rfp_real)
        config = get_demand_config(tipo)

        # 2. catalog entregaveis (+ generic LLM fallback)
        entregaveis = build_entregaveis(tipo)
        if tipo == "generic":
            entregaveis = await _gerar_entregaveis_genericos(ctx)
            agents_fired.append("Agente Genérico (LLM)")

        # 3. parallel LLM details
        tasks: list = []
        labels: list[str] = []

        abap_objects = [e for e in entregaveis if e.get("mod") == "ABAP"]
        if abap_objects:
            tasks.append(_detalhar_abap(ctx, abap_objects))
            labels.append("Agente ABAP")

        for mod in FUNCTIONAL_MODULES:
            if any(e.get("mod") == mod for e in entregaveis):
                tasks.append(_detalhar_modulo_funcional(ctx, mod, entregaveis))
                labels.append(f"Agente {mod} (detalhamento)")

        tasks.append(_gerar_as_is_to_be(ctx))
        labels.append("Processo AS-IS/TO-BE")

        results_par = await asyncio.gather(*tasks, return_exceptions=True)
        as_is = results_par[-1] if not isinstance(results_par[-1], Exception) else {}
        agents_fired.extend(labels)

        # 4. team (deterministic) + per-tenant calibration multiplier
        total_horas_entregaveis = sum(
            int(e.get("horas", 0) or 0) for e in entregaveis if isinstance(e, dict)
        )
        recursos = calculate_team(tipo, total_horas_entregaveis)
        if profile.hours_multiplier != 1.0:
            for r in recursos:
                r["dias"] = max(1, round(r.get("dias", 0) * profile.hours_multiplier))
        agents_fired.append("Equipe (calculada)")
        total_horas = sum(r.get("dias", 0) * 8 for r in recursos)

        # 5. premissas + exclusões
        premissas = filter_premissas(PREMISSAS_PADRAO, rfp_real)
        exclusoes = list(EXCLUSOES_PADRAO)
        if config.get("complexity") == "baixa":
            exclusoes.append("Não contempla customizações além do escopo descrito acima")

        # 6. comercial (tariff comes from the calibration profile)
        tarifa_hora = profile.tariff_hora
        valor = round(total_horas * tarifa_hora)

        # 7. assemble PS (Proposta de Solução)
        ver_label = SAP_VERSION_LABELS.get(self.payload.sap_version, self.payload.sap_version)
        if rfp_real:
            titulo = (
                f"{config['label']} — {rfp_real[:50]}"
                if config["label"] != "Demanda Customizada"
                else f"PS — {rfp_real[:60]}"
            )
        else:
            titulo = config.get("label", "Proposta SAP")

        entregaveis = filter_entregaveis(entregaveis)

        ps = {
            "titulo": titulo,
            "cliente": client_name,
            "tipo_projeto": self.payload.project_type,
            "tipo_demanda": tipo,
            "label_demanda": config["label"],
            "versao_sap": ver_label,
            "ufs": ufs,
            # Customer-facing fields keep the real RFP. LLM-derived fields
            # were produced from the anonymized prompt — see anonymizer
            # rationale in module docstring.
            "necessidade": rfp_real or "Adequação conforme demanda do cliente.",
            "processo_atual": as_is.get("processo_atual", ""),
            "processo_futuro": as_is.get("processo_futuro", ""),
            "beneficio_esperado": as_is.get("beneficio", ""),
            "sistema_sap": config.get("sistema_sap", ""),
            "fluxo_solucao": config.get("fluxo_solucao", ""),
            "entregaveis": entregaveis,
            "premissas": premissas,
            "exclusoes": exclusoes,
            "equipe": recursos,
            "total_horas": total_horas,
            "impactos": [
                {
                    "id": "01",
                    "descricao": "Erros durante o Go-Live",
                    "probabilidade": "Baixa",
                    "impacto": "Gravíssimo",
                    "classificacao": "Extremo",
                    "solucao": "Recuperação do backup antes da solução",
                },
                {
                    "id": "02",
                    "descricao": "Engajamento dos Key Users",
                    "probabilidade": "Baixa",
                    "impacto": "Leve",
                    "classificacao": "Baixo",
                    "solucao": "Destacar comprometimento no Kick-off",
                },
            ],
            "plano": {
                "main_proc": config.get("main_proc", "SD"),
                "modules": config.get("modules", []),
                "complexity": config.get("complexity", "media"),
                "needs_cpi": config.get("needs_cpi", False),
                "needs_basis": config.get("needs_basis", False),
                "needs_abap": "ABAP" in config.get("modules", []),
            },
            "fiscal": {
                "legislacao": [],
                "estadual": (
                    {"ativo": True}
                    if config.get("fiscal_scope", {}).get("estadual")
                    else {}
                ),
            },
            "comercial": {
                "valor_referencia": valor,
                "tarifa_hora": tarifa_hora,
                "faturamento": "50% aprovação + 50% Go-Live",
                "garantia": "30 dias corridos",
                "validade": "30 dias",
            },
        }

        # 8. QA review
        qa = await _qa_review(ctx, ps)
        agents_fired.append("QA (LLM)")
        qa_score = qa.get("score", 80)
        ps["qa_score"] = qa_score
        ps["qa_aprovado"] = qa.get("aprovado", True)
        ps["qa_problemas"] = qa.get("problemas", [])
        ps["qa_sugestoes"] = qa.get("sugestoes", [])
        # Profile sets a stricter floor — UI / approval flow can read this
        # to decide whether human review is required.
        ps["qa_min_score"] = profile.qa_min_score
        ps["qa_needs_review"] = qa_score < profile.qa_min_score

        ps["calibration"] = {
            "profile": profile.name,
            "hours_multiplier": profile.hours_multiplier,
            "tariff_hora": profile.tariff_hora,
            "confidence_penalty": profile.confidence_penalty,
        }

        confidence = {
            "escopo": 0.92 if tipo != "generic" else 0.65,
            "horas": 0.88 if tipo != "generic" else 0.70,
            "legislacao": 0.91,
            "comercial": 0.95,
        }
        if profile.confidence_penalty:
            confidence = {
                k: max(0.0, min(1.0, v - profile.confidence_penalty))
                for k, v in confidence.items()
            }

        return {
            "main_proc": config.get("main_proc", "SD"),
            "total_hours": total_horas,
            "wp_resources": recursos,
            "confidence": confidence,
            "agents_fired": agents_fired,
            "ps": ps,
            "billing_records": list(self.llm.billing),
        }

    async def _fetch_rag_preamble(self, query: str) -> str:
        """Tenant-scoped RAG retrieval. Returns a preamble string ready to
        prepend to LLM user messages, or "" when disabled / nothing found
        / any error. Never raises — catalog path is authoritative.
        """
        if self.rag is None or not _rag_enabled_for_tenant(self.tenant):
            return ""
        tenant_id = getattr(self.tenant, "id", None)
        if not tenant_id or not query.strip():
            return ""
        try:
            chunks = await self.rag.search(
                tenant_id=str(tenant_id),
                query=query,
                purpose=RAG_PURPOSE,
                limit=RAG_TOP_K,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("orchestrator_rag_search_failed", error=str(exc))
            return ""
        return _format_rag_preamble(chunks)
