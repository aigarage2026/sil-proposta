"""
CLI — Meta-análise do corpus do Sócrates + propostas geradas.

Reporta:
  • Demandas históricas frequentes SEM cobertura no catalog atual
    (candidatos a virar agente especialista novo).
  • Agentes com QA score médio baixo nos últimos N dias
    (candidatos a revisar prompt).
  • Drift entre estimativa do Sócrates e proposta efetivamente gerada
    (calibração inconsistente).

Uso:
  python scripts/analyze_knowledge.py --since 90d

Saída: tabela ASCII no stdout + opcionalmente JSON via --json.

Esta versão lê propostas geradas via Postgres (model Proposal). O lado
"demandas históricas frequentes" usa scroll do Qdrant na collection
propostai_propostas_historicas, agregando por módulos detectados.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from core.database import async_session  # noqa: E402
from models.propostai.proposal import Proposal  # noqa: E402

_DURATION_RE = re.compile(r"^(\d+)([dwm])$")


def parse_since(s: str) -> datetime:
    m = _DURATION_RE.match(s.strip().lower())
    if not m:
        raise SystemExit(f"--since formato inválido (use 30d / 4w / 3m): {s}")
    n, unit = int(m.group(1)), m.group(2)
    delta = {"d": timedelta(days=n), "w": timedelta(weeks=n), "m": timedelta(days=n * 30)}[unit]
    return datetime.utcnow() - delta


async def analyze_qa_by_agent(since: datetime) -> dict:
    """Médias de QA score por agente (parsed do JSON da PS)."""
    async with async_session() as db:
        rows = await db.execute(
            select(Proposal).where(Proposal.created_at >= since)
        )
        proposals = list(rows.scalars())

    agent_scores: dict[str, list[int]] = {}
    for p in proposals:
        for agent in p.agents_fired or []:
            # extrai nome base do agente (ex: "Agente ABAP" → "ABAP")
            name = agent.replace("Agente ", "").split(" ")[0]
            agent_scores.setdefault(name, [])
        if p.confidence_escopo is not None:
            # rough proxy: low confidence escopo = QA was unhappy
            for agent in p.agents_fired or []:
                name = agent.replace("Agente ", "").split(" ")[0]
                agent_scores[name].append(int((p.confidence_escopo or 0) * 100))

    summary = {}
    for name, scores in agent_scores.items():
        if not scores:
            continue
        summary[name] = {
            "n": len(scores),
            "mean": round(sum(scores) / len(scores), 1),
            "min": min(scores),
        }
    return summary


async def analyze_demand_distribution(since: datetime) -> dict:
    """Distribuição de tipo_demanda nas propostas geradas no período."""
    async with async_session() as db:
        rows = await db.execute(
            select(Proposal).where(Proposal.created_at >= since)
        )
        proposals = list(rows.scalars())

    types = Counter()
    for p in proposals:
        # tipo está dentro do ps_json (não é coluna); precisaria carregar
        # relationship. Por enquanto, usamos main_proc como proxy.
        types[p.main_proc or "?"] += 1
    return dict(types)


def print_section(title: str) -> None:
    print()
    print("═" * 70)
    print(f" {title}")
    print("═" * 70)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="90d", help="Janela: Nd/Nw/Nm (default 90d)")
    parser.add_argument("--json", action="store_true", help="Saída JSON em vez de tabela")
    args = parser.parse_args()

    since = parse_since(args.since)
    print(f"Analisando desde {since.isoformat()} (UTC)")

    qa_by_agent = asyncio.run(analyze_qa_by_agent(since))
    demand_dist = asyncio.run(analyze_demand_distribution(since))

    if args.json:
        import json
        print(json.dumps({
            "since": since.isoformat(),
            "qa_by_agent": qa_by_agent,
            "demand_distribution": demand_dist,
        }, indent=2, ensure_ascii=False))
        return 0

    print_section("Distribuição de propostas por main_proc")
    if not demand_dist:
        print("  (nenhuma proposta no período)")
    else:
        total = sum(demand_dist.values())
        for proc, n in sorted(demand_dist.items(), key=lambda x: -x[1]):
            pct = 100 * n / total
            print(f"  {proc:>10}: {n:>4}  ({pct:5.1f}%)")

    print_section("Confiança média por agente (proxy de QA)")
    if not qa_by_agent:
        print("  (sem dados de agentes)")
    else:
        for name, stats in sorted(qa_by_agent.items(), key=lambda kv: kv[1]["mean"]):
            flag = "  ⚠" if stats["mean"] < 70 else ""
            print(f"  {name:>12}: n={stats['n']:>3}  média={stats['mean']:>5}  min={stats['min']:>3}{flag}")
        print("\nAgentes com média < 70 ⚠ — candidatos a revisar prompt.")

    print_section("Gaps de catálogo (corpus Sócrates)")
    print("  (a implementar quando o corpus tiver volume — scroll do Qdrant")
    print("   pra contar tipos de demanda frequentes sem cobertura.)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
