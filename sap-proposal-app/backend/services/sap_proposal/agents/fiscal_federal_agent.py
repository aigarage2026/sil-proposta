"""Agente Fiscal Federal (Fabio Mendes)."""
from services.sap_proposal.agents.base_agent import BaseAgent

SYSTEM = """Agente Fiscal Federal. IPI, PIS/COFINS, Reforma Tributaria LC 214.
Retorne JSON:
{"legislacao":["NT 2024.002"],"entregaveis":[{"mod":"FISCAL","item":"descricao"}],"horas":8,"alertas":[]}
Sem markdown."""

class FiscalFederalAgent(BaseAgent):
    name = "Fabio (Fiscal Federal)"
    agent_id = "ffed"
    def _system_prompt(self): return SYSTEM
