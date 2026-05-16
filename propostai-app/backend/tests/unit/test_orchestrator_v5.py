"""
Unit tests for OrchestratorV5 (services/propostai/agents/orchestrator_v5.py).

Strategy: inject a stub LLMClient that records every call and returns
scripted responses. Catalog logic is exercised end-to-end (deterministic);
LLM-derived fields are sourced from the stub's scripted replies.

Coverage:
  - run() returns the expected shape (main_proc, total_hours, wp_resources,
    confidence, agents_fired, ps, billing_records)
  - PS carries the real RFP in `necessidade` even when anonymization is on
  - Anonymizer runs on the prompt the LLM actually sees (CPF/CNPJ masked)
  - When tenant has lgpd_anonymize_llm=False, LLM receives the raw RFP
  - billing_records flow back to the caller from the LLMClient
  - Generic demand path triggers the GENERIC agent and absorbs its output
  - LLM errors don't break the run — empty dicts substitute for those fields
"""
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional

import pytest

from services.propostai.agents.llm_client import BillingRecord, LLMClient
from services.propostai.agents.orchestrator_v5 import OrchestratorV5

pytestmark = pytest.mark.unit


# ── stub LLM ────────────────────────────────────────────────────────────────


@dataclass
class _RecordedCall:
    system: str
    user: str
    agent_name: str
    max_tokens: int


@dataclass
class _StubLLM(LLMClient):
    """LLMClient subclass that records calls and returns scripted JSON.

    `responses_by_agent` maps agent_name → response string. Anything not
    matched falls back to `default_response`. Raise via `raise_for_agent`.
    """
    responses_by_agent: dict[str, str] = field(default_factory=dict)
    default_response: str = "{}"
    raise_for_agent: set[str] = field(default_factory=set)
    calls: list[_RecordedCall] = field(default_factory=list)

    async def call(self, *, system, user, agent_name="", max_tokens=2000):  # type: ignore[override]
        self.calls.append(_RecordedCall(system, user, agent_name, max_tokens))
        if agent_name in self.raise_for_agent:
            raise RuntimeError(f"forced failure for {agent_name}")
        text = self.responses_by_agent.get(agent_name, self.default_response)
        # Tally a billing record so tests can verify the record path.
        self.billing.append(
            BillingRecord(
                model_name="stub-model",
                agent_name=agent_name,
                tokens_input=len(user),
                tokens_output=len(text),
            )
        )
        return text


def _stub_payload(
    *,
    rfp_text: str = "Implementação cBenef NT 2019.001 em SP",
    states=("SP",),
    sap_version: str = "ecc605",
    project_type: str = "Adequação Fiscal",
    client_name: Optional[str] = None,
):
    return SimpleNamespace(
        rfp_text=rfp_text,
        states=list(states),
        sap_version=sap_version,
        project_type=project_type,
        client_name=client_name,
    )


def _tenant(
    *,
    anonymize: bool = True,
    rag_enabled: bool = False,
    tenant_id: str = "t-1",
    agent_profile: Optional[str] = None,
):
    features = {"lgpd_anonymize_llm": anonymize, "rag_enabled": rag_enabled}
    if agent_profile is not None:
        features["agent_profile"] = agent_profile
    return SimpleNamespace(id=tenant_id, features=features)


# ── stub RAG ────────────────────────────────────────────────────────────────


@dataclass
class _RecordedSearch:
    tenant_id: str
    query: str
    purpose: str
    limit: int


@dataclass
class _StubRAG:
    """Minimal RAGService-shaped stub. Records search() calls and returns
    scripted chunks (default: empty). Set `raise_on_search` to simulate
    Qdrant being down.
    """
    chunks: list[dict] = field(default_factory=list)
    raise_on_search: bool = False
    calls: list[_RecordedSearch] = field(default_factory=list)

    async def search(self, *, tenant_id, query, purpose=None, limit=5):
        self.calls.append(_RecordedSearch(tenant_id, query, purpose or "", limit))
        if self.raise_on_search:
            raise RuntimeError("simulated qdrant outage")
        return list(self.chunks)


# ── happy path ─────────────────────────────────────────────────────────────


async def test_run_returns_expected_top_level_shape():
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()

    for key in ("main_proc", "total_hours", "wp_resources", "confidence",
                "agents_fired", "ps", "billing_records"):
        assert key in out, f"missing key in run() output: {key}"

    assert out["main_proc"] == "SD"  # cbenef.main_proc
    assert isinstance(out["wp_resources"], list) and out["wp_resources"]
    assert isinstance(out["agents_fired"], list)
    assert out["agents_fired"][0].startswith("Classificador")


async def test_run_uses_catalog_to_build_ps_for_known_demand():
    llm = _StubLLM()
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    ps = out["ps"]
    assert ps["tipo_demanda"] == "cbenef"
    assert ps["label_demanda"].startswith("Implementação cBenef")
    assert ps["plano"]["modules"] == ["SD", "ABAP"]
    # entregaveis built from catalog should be non-empty.
    assert ps["entregaveis"]
    # comercial calculated from total_horas * 250
    assert ps["comercial"]["tarifa_hora"] == 250
    assert ps["comercial"]["valor_referencia"] == out["total_hours"] * 250


async def test_ps_keeps_real_rfp_in_necessidade_even_with_anonymization():
    rfp_with_cnpj = "Cliente CNPJ 12.345.678/0001-90 quer cBenef em SP."
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(rfp_text=rfp_with_cnpj),
        tenant=_tenant(anonymize=True),
        llm=llm,
    )
    out = await orch.run()
    # Customer-facing field has the raw value.
    assert out["ps"]["necessidade"] == rfp_with_cnpj
    # But the LLM never saw it.
    for call in llm.calls:
        assert "12.345.678/0001-90" not in call.user


async def test_lgpd_off_passes_raw_rfp_to_llm():
    rfp_with_cnpj = "Cliente CNPJ 12.345.678/0001-90 quer cBenef em SP."
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(rfp_text=rfp_with_cnpj),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    await orch.run()
    # At least one LLM call carries the raw CNPJ.
    assert any("12.345.678/0001-90" in c.user for c in llm.calls)


async def test_billing_records_propagate_to_caller():
    llm = _StubLLM()
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    # Multiple LLM calls happened (ABAP per-item, modules, AS-IS, QA).
    assert len(out["billing_records"]) >= 3
    # Records mention agent names we expect.
    agent_names = {r.agent_name for r in out["billing_records"]}
    assert "ABAP" in agent_names or "QA" in agent_names or "AS_IS_TO_BE" in agent_names


# ── as-is / to-be content flow ─────────────────────────────────────────────


async def test_as_is_to_be_text_flows_from_llm_into_ps():
    llm = _StubLLM(
        responses_by_agent={
            "AS_IS_TO_BE": (
                '{"processo_atual":"Estado atual descrito",'
                ' "processo_futuro":"Estado futuro descrito",'
                ' "beneficio":"Conformidade fiscal e produtividade"}'
            ),
        }
    )
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    assert out["ps"]["processo_atual"] == "Estado atual descrito"
    assert out["ps"]["processo_futuro"] == "Estado futuro descrito"
    assert out["ps"]["beneficio_esperado"] == "Conformidade fiscal e produtividade"


# ── generic demand fallback ────────────────────────────────────────────────


async def test_generic_demand_invokes_generic_agent():
    llm = _StubLLM(
        responses_by_agent={
            "GENERIC": (
                '{"entregaveis":[{"mod":"SD","item":"Configuração SD específica do cliente",'
                ' "horas":24,"fase":"Realize"}]}'
            ),
        }
    )
    orch = OrchestratorV5(
        payload=_stub_payload(rfp_text="Algo totalmente fora do catálogo padrão."),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()
    assert out["ps"]["tipo_demanda"] == "generic"
    assert any("Agente Genérico" in a for a in out["agents_fired"])
    # Entregável veio do LLM e passou pelo filter (sem placeholders).
    assert any(
        e["item"] == "Configuração SD específica do cliente"
        for e in out["ps"]["entregaveis"]
    )


# ── QA flow ────────────────────────────────────────────────────────────────


async def test_qa_score_flows_into_ps():
    llm = _StubLLM(
        responses_by_agent={
            "QA": '{"aprovado":true,"score":95,"problemas":[],"sugestoes":["Adicionar item X"]}',
        }
    )
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    assert out["ps"]["qa_score"] == 95
    assert out["ps"]["qa_aprovado"] is True
    assert out["ps"]["qa_sugestoes"] == ["Adicionar item X"]


# ── failure tolerance ─────────────────────────────────────────────────────


async def test_llm_failures_do_not_break_run():
    # All LLM agents raise — orchestrator still returns a valid PS (catalog wins).
    llm = _StubLLM(
        raise_for_agent={"AS_IS_TO_BE", "ABAP", "SD", "QA"},
        default_response="not_json",
    )
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()

    assert out["ps"]["tipo_demanda"] == "cbenef"
    # AS-IS fields fell back to empty.
    assert out["ps"]["processo_atual"] == ""
    # QA fell back to its default open-pass dict.
    assert out["ps"]["qa_aprovado"] is True


async def test_default_tenant_assumes_anonymize_on():
    # No tenant passed → should_anonymize_for_tenant returns True →
    # the LLM should not see CPF.
    rfp = "Owner CPF 111.222.333-44 vai aprovar."
    llm = _StubLLM()
    orch = OrchestratorV5(payload=_stub_payload(rfp_text=rfp), tenant=None, llm=llm)
    await orch.run()
    for call in llm.calls:
        assert "111.222.333-44" not in call.user


# ── sap_version label ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ecc604", "ECC ≤ 6.04"),
        ("ecc605", "ECC 6.05+"),
        ("s4op", "S/4HANA On-premise"),
        ("s4cloud", "S/4HANA Cloud"),
    ],
)
async def test_sap_version_labels_resolved(raw, expected):
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(sap_version=raw),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()
    assert out["ps"]["versao_sap"] == expected


async def test_unknown_sap_version_passes_through():
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(sap_version="custom_version"),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()
    assert out["ps"]["versao_sap"] == "custom_version"


# ── RAG wiring (Onda 5 close) ──────────────────────────────────────────────


async def test_rag_disabled_by_default_no_search_calls():
    # Tenant has no rag_enabled flag → orchestrator must not call rag.search().
    rag = _StubRAG()
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False),  # rag_enabled defaults False
        llm=_StubLLM(),
        rag=rag,
    )
    await orch.run()
    assert rag.calls == []


async def test_rag_skipped_when_service_is_none_even_if_opted_in():
    # Opt-in only matters when a RAGService is wired. None → no-op.
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, rag_enabled=True),
        llm=_StubLLM(),
        rag=None,
    )
    out = await orch.run()
    # Still completes, no "RAG" agent fired.
    assert not any(a.startswith("RAG") for a in out["agents_fired"])


async def test_rag_context_injected_into_llm_prompts_when_enabled():
    rag = _StubRAG(
        chunks=[
            {"id": "c1", "score": 0.91, "payload": {"text": "NT 2019.001 detalha cBenef..."}},
            {"id": "c2", "score": 0.88, "payload": {"text": "Decreto SP 65.254 regulamenta..."}},
        ]
    )
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, rag_enabled=True),
        llm=llm,
        rag=rag,
    )
    out = await orch.run()

    # Search ran once, scoped to the tenant + correct purpose.
    assert len(rag.calls) == 1
    assert rag.calls[0].tenant_id == "t-1"
    assert rag.calls[0].purpose == "legislacao"

    # agents_fired records the retrieval step.
    assert any(a.startswith("RAG") for a in out["agents_fired"])

    # Every descriptive LLM call carries the preamble (catalog-driven
    # demand cbenef → AS_IS_TO_BE + ABAP + SD all see the chunks).
    descriptive_calls = [c for c in llm.calls if c.agent_name in {"AS_IS_TO_BE", "ABAP", "SD"}]
    assert descriptive_calls, "expected at least one descriptive LLM call"
    for c in descriptive_calls:
        assert "Contexto recuperado" in c.user
        assert "NT 2019.001" in c.user
        assert "Decreto SP 65.254" in c.user

    # QA gets a summary, not the RFP → no preamble expected.
    qa_calls = [c for c in llm.calls if c.agent_name == "QA"]
    assert qa_calls and "Contexto recuperado" not in qa_calls[0].user


async def test_rag_search_failure_does_not_break_run():
    # Qdrant down → RAG silently returns "" and the orchestrator proceeds.
    rag = _StubRAG(raise_on_search=True)
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, rag_enabled=True),
        llm=llm,
        rag=rag,
    )
    out = await orch.run()

    # Search was attempted, but the failure was swallowed.
    assert len(rag.calls) == 1
    # No RAG agent in the fired list (preamble is empty).
    assert not any(a.startswith("RAG") for a in out["agents_fired"])
    # No prompt should mention the preamble header.
    assert all("Contexto recuperado" not in c.user for c in llm.calls)


async def test_rag_uses_anonymized_query():
    # The RAG search query must be the anonymized RFP, not the raw one —
    # the corpus is public legislation; sending real PII to vendor APIs
    # would defeat the LGPD anonymizer.
    rag = _StubRAG(chunks=[{"id": "c", "score": 0.5, "payload": {"text": "ctx"}}])
    rfp_with_cpf = "Owner CPF 111.222.333-44 quer cBenef em SP"
    orch = OrchestratorV5(
        payload=_stub_payload(rfp_text=rfp_with_cpf),
        tenant=_tenant(anonymize=True, rag_enabled=True),
        llm=_StubLLM(),
        rag=rag,
    )
    await orch.run()
    assert len(rag.calls) == 1
    assert "111.222.333-44" not in rag.calls[0].query


# ── Calibration profiles (Onda 5 close — E9 / H2 / H3) ────────────────────


async def test_default_profile_does_not_change_baseline():
    # Baseline: no tenant feature set → multiplier 1.0, tariff 250, no penalty.
    llm = _StubLLM()
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    assert out["ps"]["comercial"]["tarifa_hora"] == 250
    assert out["ps"]["calibration"]["profile"] == "default"
    assert out["ps"]["calibration"]["hours_multiplier"] == 1.0
    # Confidence unchanged from the catalog defaults.
    assert out["confidence"]["escopo"] == 0.92


async def test_conservative_profile_inflates_hours_and_value():
    # Run twice (default vs conservative) and compare. Conservative must
    # produce strictly more hours and value (multiplier 1.5).
    llm_default = _StubLLM()
    out_default = await OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False),
        llm=llm_default,
    ).run()

    llm_cons = _StubLLM()
    out_cons = await OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, agent_profile="conservative"),
        llm=llm_cons,
    ).run()

    assert out_cons["total_hours"] > out_default["total_hours"]
    assert (
        out_cons["ps"]["comercial"]["valor_referencia"]
        > out_default["ps"]["comercial"]["valor_referencia"]
    )
    # Confidence is penalized; QA threshold is stricter.
    assert out_cons["confidence"]["escopo"] < out_default["confidence"]["escopo"]
    assert out_cons["ps"]["qa_min_score"] == 90
    assert out_cons["ps"]["calibration"]["profile"] == "conservative"
    # agents_fired records which profile was applied.
    assert any("conservative" in a for a in out_cons["agents_fired"])


async def test_aggressive_profile_deflates_hours():
    llm_default = _StubLLM()
    out_default = await OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False),
        llm=llm_default,
    ).run()

    llm_agg = _StubLLM()
    out_agg = await OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, agent_profile="aggressive"),
        llm=llm_agg,
    ).run()

    assert out_agg["total_hours"] <= out_default["total_hours"]
    # No confidence penalty on aggressive — speed bias, not honesty bias.
    assert out_agg["confidence"]["escopo"] == out_default["confidence"]["escopo"]


async def test_conservative_profile_flags_qa_needs_review_when_score_low():
    # QA returns 85; conservative requires 90 → needs_review must be True.
    llm = _StubLLM(
        responses_by_agent={
            "QA": '{"aprovado":true,"score":85,"problemas":[],"sugestoes":[]}',
        }
    )
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, agent_profile="conservative"),
        llm=llm,
    )
    out = await orch.run()
    assert out["ps"]["qa_score"] == 85
    assert out["ps"]["qa_needs_review"] is True


async def test_default_profile_does_not_flag_qa_when_above_default_threshold():
    llm = _StubLLM(
        responses_by_agent={
            "QA": '{"aprovado":true,"score":85,"problemas":[],"sugestoes":[]}',
        }
    )
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()
    assert out["ps"]["qa_needs_review"] is False


async def test_unknown_profile_name_falls_back_silently():
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, agent_profile="ultra-mega-cons"),
        llm=llm,
    )
    out = await orch.run()
    # Behaves like default.
    assert out["ps"]["calibration"]["profile"] == "default"


async def test_rag_empty_results_produce_no_preamble():
    # Search returned [] (no indexed corpus matches) → no preamble injected
    # and no "RAG" agent fired, even though the search itself ran.
    rag = _StubRAG(chunks=[])
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(),
        tenant=_tenant(anonymize=False, rag_enabled=True),
        llm=llm,
        rag=rag,
    )
    out = await orch.run()
    assert len(rag.calls) == 1
    assert not any(a.startswith("RAG") for a in out["agents_fired"])
    assert all("Contexto recuperado" not in c.user for c in llm.calls)
