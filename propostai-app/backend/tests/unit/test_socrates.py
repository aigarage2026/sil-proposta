"""
Unit tests para o agente Sócrates (services/propostai/agents/socrates.py).

Cobre:
  - consult() devolve briefing vazio quando rag=None / query vazia / sem hits
  - synthesize() agrega módulos por frequência ≥ 40% dos hits
  - synthesize() calcula mediana e faixa p25/p75 quando hours samples ≥ 4
  - briefing.is_actionable() só vira True com ≥ MIN_MATCHES_FOR_PATTERN
  - briefing.as_prompt_preamble() vazio quando não actionable
  - assess_against_briefing flagra sub-dimensionamento e over-engineering
"""
from dataclasses import dataclass, field
from typing import Any

import pytest

from services.propostai.agents.socrates import (
    Socrates,
    SocratesBriefing,
    assess_against_briefing,
)

pytestmark = pytest.mark.unit


# ── stub RAG ───────────────────────────────────────────────────────────────


@dataclass
class _StubRAG:
    hits: list[dict] = field(default_factory=list)
    raise_on_search: bool = False
    calls: list = field(default_factory=list)

    async def search(self, *, tenant_id, query, purpose=None, limit=5):
        self.calls.append({"tenant_id": tenant_id, "query": query, "purpose": purpose})
        if self.raise_on_search:
            raise RuntimeError("simulated")
        return list(self.hits)


def _hit(score: float, **payload: Any) -> dict:
    return {"id": payload.pop("id", "h"), "score": score, "payload": payload}


# ── consult() ──────────────────────────────────────────────────────────────


async def test_consult_returns_empty_when_rag_is_none():
    b = await Socrates(rag=None).consult("anything")
    assert b.demandas_semelhantes_encontradas == 0
    assert b.is_actionable() is False


async def test_consult_returns_empty_for_empty_query():
    rag = _StubRAG(hits=[_hit(0.9, modules=["SD"])])
    b = await Socrates(rag=rag).consult("")
    assert b.demandas_semelhantes_encontradas == 0
    # Não chamou search.
    assert rag.calls == []


async def test_consult_swallows_search_errors():
    rag = _StubRAG(raise_on_search=True)
    b = await Socrates(rag=rag).consult("alguma RFP")
    assert b.demandas_semelhantes_encontradas == 0


async def test_consult_returns_empty_when_no_hits():
    rag = _StubRAG(hits=[])
    b = await Socrates(rag=rag).consult("RFP")
    assert b.demandas_semelhantes_encontradas == 0


# ── synthesize / aggregation ──────────────────────────────────────────────


async def test_synthesize_picks_modules_at_or_above_40pct_frequency():
    # 5 hits, SD em 4 (80%), FI em 2 (40%), ABAP em 1 (20%).
    hits = [
        _hit(0.9, modules=["SD", "FI"]),
        _hit(0.9, modules=["SD"]),
        _hit(0.9, modules=["SD", "FI"]),
        _hit(0.9, modules=["SD"]),
        _hit(0.9, modules=["ABAP"]),
    ]
    rag = _StubRAG(hits=hits)
    b = await Socrates(rag=rag).consult("q")
    assert "SD" in b.padrao_modulos
    assert "FI" in b.padrao_modulos
    assert "ABAP" not in b.padrao_modulos


async def test_synthesize_computes_hours_median_and_band():
    hits = [
        _hit(0.9, modules=["SD"], hours=100),
        _hit(0.9, modules=["SD"], hours=200),
        _hit(0.9, modules=["SD"], hours=300),
        _hit(0.9, modules=["SD"], hours=400),
    ]
    rag = _StubRAG(hits=hits)
    b = await Socrates(rag=rag).consult("q")
    assert b.horas_mediana == 250  # mediana de [100,200,300,400]
    assert b.horas_p25_p75 is not None
    p25, p75 = b.horas_p25_p75
    assert p25 <= b.horas_mediana <= p75


async def test_synthesize_no_hours_band_when_fewer_than_4_samples():
    hits = [
        _hit(0.9, modules=["SD"], hours=100),
        _hit(0.9, modules=["SD"], hours=200),
    ]
    rag = _StubRAG(hits=hits)
    b = await Socrates(rag=rag).consult("q")
    # Below the per-band threshold (needs ≥4 hours samples).
    assert b.horas_p25_p75 is None


async def test_synthesize_extracts_repeated_entregaveis_and_riscos():
    hits = [
        _hit(0.9, modules=["SD"],
             entregaveis=["BAdI X", "Tabela Z"], riscos=["Rejeição 931"]),
        _hit(0.9, modules=["SD"],
             entregaveis=["BAdI X"], riscos=["Rejeição 931", "Atraso"]),
        _hit(0.9, modules=["SD"],
             entregaveis=["Tabela Z"], riscos=["Atraso"]),
    ]
    rag = _StubRAG(hits=hits)
    b = await Socrates(rag=rag).consult("q")
    # BAdI X aparece 2x → entra. Items que aparecem só 1x não.
    assert "BAdI X" in b.entregaveis_recorrentes
    assert "Tabela Z" in b.entregaveis_recorrentes
    assert "Rejeição 931" in b.riscos_recorrentes
    assert "Atraso" in b.riscos_recorrentes


# ── briefing.is_actionable + preamble ──────────────────────────────────────


def test_briefing_actionable_threshold():
    assert SocratesBriefing(demandas_semelhantes_encontradas=2).is_actionable() is False
    assert SocratesBriefing(demandas_semelhantes_encontradas=3).is_actionable() is True


def test_preamble_empty_when_not_actionable():
    assert SocratesBriefing().as_prompt_preamble() == ""


def test_preamble_includes_pattern_summary():
    b = SocratesBriefing(
        demandas_semelhantes_encontradas=5,
        confianca_match=0.82,
        padrao_modulos=["SD", "FI"],
        horas_mediana=380,
        horas_p25_p75=(280, 520),
        entregaveis_recorrentes=["BAdI X"],
        riscos_recorrentes=["Rejeição 931"],
    )
    out = b.as_prompt_preamble()
    assert "Sócrates encontrou padrão" in out
    assert "SD, FI" in out
    assert "380h" in out
    assert "BAdI X" in out
    assert "Rejeição 931" in out


# ── assess_against_briefing ───────────────────────────────────────────────


def test_assess_returns_ok_when_briefing_empty():
    out = assess_against_briefing(proposed_hours=100, briefing=SocratesBriefing())
    assert out["alinhado"] is True
    assert out["severidade"] == "ok"


def test_assess_flags_under_dimensioned():
    b = SocratesBriefing(
        demandas_semelhantes_encontradas=5,
        horas_mediana=400, horas_p25_p75=(300, 500),
    )
    # 100h vs p25=300 → mais que 50% abaixo do p25.
    out = assess_against_briefing(proposed_hours=100, briefing=b)
    assert out["alinhado"] is False
    assert out["severidade"] == "alto"
    assert "sub-dimensionamento" in out["motivo"].lower()


def test_assess_flags_over_engineering():
    b = SocratesBriefing(
        demandas_semelhantes_encontradas=5,
        horas_mediana=400, horas_p25_p75=(300, 500),
    )
    # 1500h vs p75=500 → mais que 2x acima do p75.
    out = assess_against_briefing(proposed_hours=1500, briefing=b)
    assert out["alinhado"] is False
    assert out["severidade"] == "baixo"
    assert "over-engineering" in out["motivo"].lower()


def test_assess_aligned_within_band():
    b = SocratesBriefing(
        demandas_semelhantes_encontradas=5,
        horas_mediana=400, horas_p25_p75=(300, 500),
    )
    out = assess_against_briefing(proposed_hours=380, briefing=b)
    assert out["alinhado"] is True
    assert out["severidade"] == "ok"
