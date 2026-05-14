"""Agente Equipe / GP (Eduardo Gomes)."""
from services.sil_proposta.agents.base_agent import BaseAgent

SYSTEM = """Agente Equipe. REGRA: 4+ ABAP independentes -> 3 ABAPers paralelos. GP se projeto >3 semanas.
Retorne JSON:
{"recursos":[{"frente":"SD","nivel":"Senior","dias":9},{"frente":"FI","nivel":"Senior","dias":11},
 {"frente":"GP","nivel":"Senior","dias":4},{"frente":"ABAP 1","nivel":"Senior","dias":14},
 {"frente":"ABAP 2","nivel":"Senior","dias":14},{"frente":"ABAP 3","nivel":"Senior","dias":14}],
 "total_dias":66,"semanas":4,"gp":true}
Sem markdown."""

class EquipeAgent(BaseAgent):
    name = "Eduardo (Equipe/GP)"
    agent_id = "eq"
    def _system_prompt(self): return SYSTEM
