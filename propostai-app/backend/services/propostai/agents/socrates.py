"""
Sócrates — agente de memória/conhecimento (v3 Onda 5 close, follow-up).

Roda em TODA nova proposta (não é opt-in). Antes dos agentes
especialistas, Sócrates consulta o corpus de PSs históricas anonimizadas
e devolve um *briefing* estruturado: módulos típicos, perfil de equipe,
faixa de horas, entregáveis e riscos recorrentes em demandas similares.

O briefing é usado em dois pontos do pipeline:

  1. Enriquece o prompt dos agentes especialistas (SD/FI/ABAP/etc.) com
     o que historicamente funcionou em demandas parecidas.
  2. Vira insumo de cross-check do QA: se a proposta gerada está fora
     da distribuição histórica (horas muito menores ou maiores que a
     mediana), QA marca para revisão humana.

Princípios de design:
  - **Nunca cita** uma proposta histórica específica. Só extrai padrões
    agregados. Isso é o que justifica o corpus ser global e anonimizado.
  - **Fail-open**: se o corpus está vazio ou o Qdrant cai, Sócrates
    devolve um briefing vazio e o pipeline segue normalmente.
  - **Sem efeito colateral**: não escreve em lugar nenhum. Auto-indexar
    a PS gerada é responsabilidade de generation_service, após
    aprovação.

Sócrates SUBSTITUI o caminho RAG legado em OrchestratorV5: o
`_fetch_rag_preamble()` antigo era opt-in por tenant e devolvia chunks
crus; Sócrates é always-on e devolve estrutura sintetizada.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Optional

from core.logger import get_logger
from services.ingest.pipeline import GLOBAL_TENANT_ID, RAG_PURPOSE
from services.rag.service import RAGService

logger = get_logger()

DEFAULT_TOP_K = 10
MIN_MATCHES_FOR_PATTERN = 3  # menos que isso, briefing vai vazio


@dataclass
class SocratesBriefing:
    """O que Sócrates devolve. Pode ser vazio quando o corpus está vazio
    ou nenhum match passa do threshold.
    """
    demandas_semelhantes_encontradas: int = 0
    confianca_match: float = 0.0
    padrao_modulos: list[str] = field(default_factory=list)
    horas_mediana: Optional[int] = None
    horas_p25_p75: Optional[tuple[int, int]] = None
    entregaveis_recorrentes: list[str] = field(default_factory=list)
    riscos_recorrentes: list[str] = field(default_factory=list)

    def is_actionable(self) -> bool:
        """True se houver dados suficientes pra alimentar especialistas/QA."""
        return self.demandas_semelhantes_encontradas >= MIN_MATCHES_FOR_PATTERN

    def as_prompt_preamble(self) -> str:
        """Texto compacto pra prefixar nos prompts dos especialistas."""
        if not self.is_actionable():
            return ""
        lines = [
            "Sócrates encontrou padrão em demandas semelhantes "
            f"(N={self.demandas_semelhantes_encontradas}, "
            f"confiança={self.confianca_match:.2f}):",
        ]
        if self.padrao_modulos:
            lines.append(f"- Módulos típicos: {', '.join(self.padrao_modulos)}")
        if self.horas_mediana is not None:
            p25, p75 = self.horas_p25_p75 or (None, None)
            faixa = f"{p25}-{p75}h" if p25 and p75 else f"~{self.horas_mediana}h"
            lines.append(f"- Faixa de horas histórica: {faixa} (mediana {self.horas_mediana}h)")
        if self.entregaveis_recorrentes:
            top = self.entregaveis_recorrentes[:5]
            lines.append("- Entregáveis recorrentes: " + "; ".join(top))
        if self.riscos_recorrentes:
            top = self.riscos_recorrentes[:3]
            lines.append("- Riscos historicamente reportados: " + "; ".join(top))
        return "\n".join(lines) + "\n\n"

    def as_dict(self) -> dict[str, Any]:
        return {
            "demandas_semelhantes_encontradas": self.demandas_semelhantes_encontradas,
            "confianca_match": self.confianca_match,
            "padrao_modulos": self.padrao_modulos,
            "horas_mediana": self.horas_mediana,
            "horas_p25_p75": list(self.horas_p25_p75) if self.horas_p25_p75 else None,
            "entregaveis_recorrentes": self.entregaveis_recorrentes,
            "riscos_recorrentes": self.riscos_recorrentes,
        }


@dataclass
class Socrates:
    """O agente. Recebe RAGService injetado, fala com Qdrant via ele.
    Mantém o teste fácil — basta passar um stub do RAGService.
    """
    rag: Optional[RAGService] = None
    top_k: int = DEFAULT_TOP_K

    async def consult(self, query: str) -> SocratesBriefing:
        """Consulta o corpus e devolve o briefing. Nunca raise."""
        if self.rag is None or not (query or "").strip():
            return SocratesBriefing()
        try:
            hits = await self.rag.search(
                tenant_id=GLOBAL_TENANT_ID,
                query=query,
                purpose=RAG_PURPOSE,
                limit=self.top_k,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("socrates_search_failed", error=str(exc))
            return SocratesBriefing()

        if not hits:
            return SocratesBriefing()

        return self._synthesize(hits)

    def _synthesize(self, hits: list[dict]) -> SocratesBriefing:
        """Agrega métricas dos top-k hits em padrões."""
        modules_counter: Counter[str] = Counter()
        hours_samples: list[int] = []
        entregaveis_samples: list[str] = []
        riscos_samples: list[str] = []

        scores: list[float] = []
        for h in hits:
            scores.append(float(h.get("score", 0.0)))
            payload = h.get("payload") or {}

            for m in payload.get("modules", []) or []:
                modules_counter[m] += 1

            # The historical metadata extractor doesn't capture hours
            # directly (we don't trust LLM-parsed hours from old DAMs),
            # so we use size_band as a coarse proxy when explicit hours
            # are absent.
            horas = payload.get("hours")
            if isinstance(horas, (int, float)) and horas > 0:
                hours_samples.append(int(horas))

            for e in payload.get("entregaveis", []) or []:
                if isinstance(e, str) and e.strip():
                    entregaveis_samples.append(e.strip())

            for r in payload.get("riscos", []) or []:
                if isinstance(r, str) and r.strip():
                    riscos_samples.append(r.strip())

        confianca = sum(scores) / len(scores) if scores else 0.0

        # Modules: keep those that appeared in >= 40% of hits.
        cutoff = max(1, int(0.4 * len(hits)))
        padrao_modulos = [m for m, c in modules_counter.most_common() if c >= cutoff]

        horas_mediana = int(median(hours_samples)) if hours_samples else None
        horas_p25_p75 = _percentile_band(hours_samples) if len(hours_samples) >= 4 else None

        entregaveis_recorrentes = _top_repeated(entregaveis_samples, min_count=2, limit=10)
        riscos_recorrentes = _top_repeated(riscos_samples, min_count=2, limit=10)

        return SocratesBriefing(
            demandas_semelhantes_encontradas=len(hits),
            confianca_match=round(confianca, 3),
            padrao_modulos=padrao_modulos,
            horas_mediana=horas_mediana,
            horas_p25_p75=horas_p25_p75,
            entregaveis_recorrentes=entregaveis_recorrentes,
            riscos_recorrentes=riscos_recorrentes,
        )


def _top_repeated(items: list[str], *, min_count: int, limit: int) -> list[str]:
    """Retorna itens que apareceram >= min_count vezes, ordenado por
    frequência, deduplicado preservando case original do primeiro hit.
    """
    counter = Counter(i.lower() for i in items)
    canon: dict[str, str] = {}
    for i in items:
        canon.setdefault(i.lower(), i)
    return [canon[k] for k, c in counter.most_common(limit) if c >= min_count]


def _percentile_band(samples: list[int]) -> tuple[int, int]:
    sorted_s = sorted(samples)
    n = len(sorted_s)
    p25 = sorted_s[max(0, n // 4)]
    p75 = sorted_s[min(n - 1, (3 * n) // 4)]
    return (int(p25), int(p75))


# ── QA cross-check ─────────────────────────────────────────────────────────


def assess_against_briefing(
    proposed_hours: int,
    briefing: SocratesBriefing,
) -> dict[str, Any]:
    """Compara horas propostas vs distribuição histórica de Sócrates.

    Devolve um dict com {alinhado: bool, motivo: str|None, severidade:
    "ok"|"baixo"|"alto"}. QA usa pra decidir se requer revisão humana.
    """
    if not briefing.is_actionable() or briefing.horas_mediana is None:
        return {"alinhado": True, "motivo": None, "severidade": "ok"}

    p25, p75 = briefing.horas_p25_p75 or (None, None)
    if p25 is None or p75 is None:
        return {"alinhado": True, "motivo": None, "severidade": "ok"}

    # 50% abaixo do p25 = risco de sub-dimensionamento.
    if proposed_hours < int(p25 * 0.5):
        return {
            "alinhado": False,
            "motivo": (
                f"Proposta com {proposed_hours}h, mas demandas similares "
                f"historicamente ficaram entre {p25}-{p75}h. "
                f"Risco de sub-dimensionamento."
            ),
            "severidade": "alto",
        }
    # 100% acima do p75 = risco de over-engineering.
    if proposed_hours > int(p75 * 2.0):
        return {
            "alinhado": False,
            "motivo": (
                f"Proposta com {proposed_hours}h, mas demandas similares "
                f"historicamente ficaram entre {p25}-{p75}h. "
                f"Possível over-engineering."
            ),
            "severidade": "baixo",
        }
    return {"alinhado": True, "motivo": None, "severidade": "ok"}
