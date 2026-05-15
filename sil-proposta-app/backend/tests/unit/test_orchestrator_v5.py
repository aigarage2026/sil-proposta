"""
Unit tests for OrchestratorV5 (services/sil_proposta/agents/orchestrator_v5.py).

Strategy: inject a stub LLMClient that records every call and returns
scripted responses. Catalog logic is exercised end-to-end (deterministic);
LLM-derived fields are sourced from the stub's scripted replies.

Coverage:
  - run() returns the expected shape (main_proc, total_hours, wp_resources,
    confidence, agents_fired, dam, billing_records)
  - DAM carries the real RFP in `necessidade` even when anonymization is on
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

from services.sil_proposta.agents.llm_client import BillingRecord, LLMClient
from services.sil_proposta.agents.orchestrator_v5 import OrchestratorV5

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


def _tenant(*, anonymize: bool = True):
    return SimpleNamespace(features={"lgpd_anonymize_llm": anonymize})


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
                "agents_fired", "dam", "billing_records"):
        assert key in out, f"missing key in run() output: {key}"

    assert out["main_proc"] == "SD"  # cbenef.main_proc
    assert isinstance(out["wp_resources"], list) and out["wp_resources"]
    assert isinstance(out["agents_fired"], list)
    assert out["agents_fired"][0].startswith("Classificador")


async def test_run_uses_catalog_to_build_dam_for_known_demand():
    llm = _StubLLM()
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    dam = out["dam"]
    assert dam["tipo_demanda"] == "cbenef"
    assert dam["label_demanda"].startswith("Implementação cBenef")
    assert dam["plano"]["modules"] == ["SD", "ABAP"]
    # entregaveis built from catalog should be non-empty.
    assert dam["entregaveis"]
    # comercial calculated from total_horas * 250
    assert dam["comercial"]["tarifa_hora"] == 250
    assert dam["comercial"]["valor_referencia"] == out["total_hours"] * 250


async def test_dam_keeps_real_rfp_in_necessidade_even_with_anonymization():
    rfp_with_cnpj = "Cliente CNPJ 12.345.678/0001-90 quer cBenef em SP."
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(rfp_text=rfp_with_cnpj),
        tenant=_tenant(anonymize=True),
        llm=llm,
    )
    out = await orch.run()
    # Customer-facing field has the raw value.
    assert out["dam"]["necessidade"] == rfp_with_cnpj
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


async def test_as_is_to_be_text_flows_from_llm_into_dam():
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
    assert out["dam"]["processo_atual"] == "Estado atual descrito"
    assert out["dam"]["processo_futuro"] == "Estado futuro descrito"
    assert out["dam"]["beneficio_esperado"] == "Conformidade fiscal e produtividade"


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
        payload=_stub_payload(rfp_text="Algo totalmente fora do catálogo padrão da Cast."),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()
    assert out["dam"]["tipo_demanda"] == "generic"
    assert any("Agente Genérico" in a for a in out["agents_fired"])
    # Entregável veio do LLM e passou pelo filter (sem placeholders).
    assert any(
        e["item"] == "Configuração SD específica do cliente"
        for e in out["dam"]["entregaveis"]
    )


# ── QA flow ────────────────────────────────────────────────────────────────


async def test_qa_score_flows_into_dam():
    llm = _StubLLM(
        responses_by_agent={
            "QA": '{"aprovado":true,"score":95,"problemas":[],"sugestoes":["Adicionar item X"]}',
        }
    )
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()
    assert out["dam"]["qa_score"] == 95
    assert out["dam"]["qa_aprovado"] is True
    assert out["dam"]["qa_sugestoes"] == ["Adicionar item X"]


# ── failure tolerance ─────────────────────────────────────────────────────


async def test_llm_failures_do_not_break_run():
    # All LLM agents raise — orchestrator still returns a valid DAM (catalog wins).
    llm = _StubLLM(
        raise_for_agent={"AS_IS_TO_BE", "ABAP", "SD", "QA"},
        default_response="not_json",
    )
    orch = OrchestratorV5(payload=_stub_payload(), tenant=_tenant(anonymize=False), llm=llm)
    out = await orch.run()

    assert out["dam"]["tipo_demanda"] == "cbenef"
    # AS-IS fields fell back to empty.
    assert out["dam"]["processo_atual"] == ""
    # QA fell back to its default open-pass dict.
    assert out["dam"]["qa_aprovado"] is True


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
    assert out["dam"]["versao_sap"] == expected


async def test_unknown_sap_version_passes_through():
    llm = _StubLLM()
    orch = OrchestratorV5(
        payload=_stub_payload(sap_version="custom_version"),
        tenant=_tenant(anonymize=False),
        llm=llm,
    )
    out = await orch.run()
    assert out["dam"]["versao_sap"] == "custom_version"
