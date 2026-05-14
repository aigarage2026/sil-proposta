"""
Orquestrador — coordena execucao dos agentes IA.
Agentes independentes rodam em paralelo (ADR-015).
"""
import asyncio
import json

from core.config import get_settings
from core.logger import get_logger
from schemas.intake import IntakePayload
from services.sil_proposta.agents.base_agent import BaseAgent

settings = get_settings()
logger = get_logger()

SYSTEM_ORCH = """Voce e o orquestrador do Sil-Proposta. Analise o intake e retorne APENAS JSON:
{
  "modules": ["SD","FI","ABAP"],
  "fiscal_agents": ["estadual","federal"],
  "needs_cpi": true,
  "needs_reform": false,
  "hardware_integration": true,
  "abap_objects": ["BAPI","BAdI","RFC","iFlow","Monitor"],
  "abap_parallelism": 3,
  "reasoning": "explicacao em 1-2 linhas"
}
Sem markdown, sem texto fora do JSON."""


class OrchestratorAgent:
    """Coordena execucao de agentes com paralelismo."""

    def __init__(self, payload: IntakePayload, tenant_id: str):
        self.payload = payload
        self.tenant_id = tenant_id

    def _build_context(self) -> str:
        p = self.payload
        return (
            f"Tipo: {p.project_type} | SAP: {p.sap_version} | "
            f"UFs: {', '.join(p.states)} | Comercial: {p.commercial_model} | "
            f"Nova lei: {p.new_law} | Horas pre-venda: {p.hours_presale}\n\n"
            f"RFP:\n{p.rfp_text or 'Nao informada'}\n\n"
            f"Obs: {p.notes or 'Nenhuma'}"
        )

    async def run(self) -> dict:
        """Execucao completa: plan → agentes em paralelo → consolidacao."""
        ctx = self._build_context()
        fired = []
        results = {}

        # 1. Plano do orquestrador
        orch = BaseAgent(self.tenant_id)
        orch.name = "Orquestrador"
        orch._system_prompt = lambda: SYSTEM_ORCH
        plan = await orch.execute(ctx)
        fired.append("Orquestrador")

        # 2. Agentes paralelos (SD, FI, ABAP)
        from services.sil_proposta.agents.sd_agent import SDAgent
        from services.sil_proposta.agents.fi_agent import FIAgent
        from services.sil_proposta.agents.abap_agent import ABAPAgent

        parallel_agents = []
        for mod in plan.get("modules", ["SD", "FI", "ABAP"]):
            if mod == "SD":
                parallel_agents.append(("SD", SDAgent(self.tenant_id)))
            elif mod == "FI":
                parallel_agents.append(("FI", FIAgent(self.tenant_id)))
            elif mod == "ABAP":
                parallel_agents.append(("ABAP", ABAPAgent(self.tenant_id)))

        if parallel_agents:
            parallel_results = await asyncio.gather(
                *[agent.execute(ctx) for _, agent in parallel_agents],
                return_exceptions=True,
            )
            for (name, _), result in zip(parallel_agents, parallel_results):
                if isinstance(result, Exception):
                    logger.error(f"Agent {name} failed", error=str(result))
                else:
                    results[name] = result
                    fired.append(name)

        # 3. Agentes sequenciais (dependem dos anteriores)
        from services.sil_proposta.agents.drc_agent import DRCAgent
        from services.sil_proposta.agents.fiscal_estadual_agent import FiscalEstadualAgent
        from services.sil_proposta.agents.fiscal_federal_agent import FiscalFederalAgent
        from services.sil_proposta.agents.equipe_agent import EquipeAgent
        from services.sil_proposta.agents.comercial_agent import ComercialAgent

        # DRC
        drc = DRCAgent(self.tenant_id)
        results["DRC"] = await drc.execute(ctx)
        fired.append("DRC")

        # Fiscal paralelo
        fest_result, ffed_result = await asyncio.gather(
            FiscalEstadualAgent(self.tenant_id).execute(f"UF: {self.payload.states[0] if self.payload.states else 'SP'}\n{ctx}"),
            FiscalFederalAgent(self.tenant_id).execute(ctx),
        )
        results["FISCAL_ESTADUAL"] = fest_result
        results["FISCAL_FEDERAL"] = ffed_result
        fired.extend(["Fiscal Estadual", "Fiscal Federal"])

        # Equipe (depende de ABAP)
        eq = EquipeAgent(self.tenant_id)
        results["EQUIPE"] = await eq.execute(f"ABAP: {json.dumps(results.get('ABAP', {}))}\n{ctx}")
        fired.append("Equipe/GP")

        # Comercial (depende de equipe)
        com = ComercialAgent(self.tenant_id)
        results["COMERCIAL"] = await com.execute(f"Recursos: {json.dumps(results.get('EQUIPE', {}))}\n{ctx}")
        fired.append("Comercial")

        return self._consolidate(plan, results, fired)

    def _consolidate(self, plan: dict, results: dict, agents: list) -> dict:
        """Consolida resultados de todos os agentes em estrutura DAM."""
        eq = results.get("EQUIPE", {})
        res = eq.get("recursos", [
            {"frente": "SD", "nivel": "Senior", "dias": 9},
            {"frente": "FI", "nivel": "Senior", "dias": 11},
            {"frente": "GP", "nivel": "Senior", "dias": 4},
            {"frente": "ABAP 1", "nivel": "Senior", "dias": 14},
            {"frente": "ABAP 2", "nivel": "Senior", "dias": 14},
            {"frente": "ABAP 3", "nivel": "Senior", "dias": 14},
        ])
        th = sum(r["dias"] * 8 for r in res)

        all_e, all_p = [], []
        for v in results.values():
            if isinstance(v, dict):
                all_e.extend(v.get("entregaveis", []))
                all_p.extend(v.get("premissas", []))

        BASE_PREMISSAS = [
            "Os acessos necessarios deverao estar liberados ate o inicio do projeto.",
            "Os usuarios disponibilizados deverao ter acesso para depuracao em QAS.",
            "Todos os desenvolvimentos serao realizados em ABAP.",
            "O inicio das atividades somente apos aprovacao formal do cronograma.",
            "Gerenciamento remoto durante toda a execucao do projeto.",
            "Dia de consultoria: 8h (08h30-12h / 13h30-18h), segunda a sexta.",
            "Duvidas ou falhas devem ser reportadas durante testes.",
            "A documentacao sera entregue em lingua portuguesa.",
        ]
        premissas = BASE_PREMISSAS + [p for p in all_p if p not in BASE_PREMISSAS]

        dam = {
            "titulo": f"DAM - {(self.payload.rfp_text or 'Proposta SAP')[:60]}",
            "tipo_projeto": self.payload.project_type,
            "versao_sap": self.payload.sap_version,
            "ufs": self.payload.states,
            "necessidade": results.get("SD", {}).get("observacoes", "Adequacao fiscal e operacional."),
            "entregaveis": list({json.dumps(e): e for e in all_e}.values()),
            "premissas": premissas,
            "equipe": res,
            "total_horas": th,
            "plano": plan,
            "reforma": results.get("REFORMA", {"decisao": "monitorar"}),
            "fiscal": results.get("FISCAL_ESTADUAL", {}),
            "comercial": results.get("COMERCIAL", {}),
        }

        confidence = {
            "escopo": 0.88 if self.payload.rfp_text else 0.65,
            "horas": 0.82,
            "legislacao": 0.91 if self.payload.states else 0.70,
            "comercial": 0.95,
        }

        return {
            "dam": dam,
            "wp_resources": res,
            "total_hours": th,
            "confidence": confidence,
            "agents_fired": agents,
            "main_proc": plan.get("modules", ["SD"])[0] if plan.get("modules") else "SD",
        }
