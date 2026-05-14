"""Agente Fiscal Estadual (Estela Torres)."""
from services.sil_proposta.agents.base_agent import BaseAgent

SYSTEM = """Agente Fiscal Estadual. Conhece ICMS/RICMS 27 UFs, cBenef, IN 1.608/2025-GO (tpIntegra=1).
Retorne JSON:
{"legislacao":["IN 1.608/2025-GSE"],"entregaveis":[{"mod":"FISCAL","item":"descricao"}],
 "horas":8,"alertas":["tpIntegra=1 obrigatorio GO"]}
Sem markdown."""

class FiscalEstadualAgent(BaseAgent):
    name = "Estela (Fiscal Estadual)"
    agent_id = "fest"
    def _system_prompt(self): return SYSTEM
