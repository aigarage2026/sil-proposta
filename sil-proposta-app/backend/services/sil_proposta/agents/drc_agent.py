"""Agente DRC — Document Reporting Compliance (Diana Rocha)."""
from services.sil_proposta.agents.base_agent import BaseAgent

SYSTEM = """Agente DRC. REGRA CRITICA: ECONF (110750/110751) NAO tem suporte DRC nativo -> CPI obrigatorio.
Retorne JSON:
{"canal":"CPI","entregaveis":[{"mod":"DRC","item":"descricao"}],
 "horas":0,"justificativa":"ECONF sem nota SAP — CPI obrigatorio"}
Sem markdown."""

class DRCAgent(BaseAgent):
    name = "Diana (DRC)"
    agent_id = "drc"
    def _system_prompt(self): return SYSTEM
