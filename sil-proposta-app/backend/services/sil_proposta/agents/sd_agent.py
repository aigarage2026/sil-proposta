"""Agente SD — Sales & Distribution (Sofia Duarte)."""
from services.sil_proposta.agents.base_agent import BaseAgent

SYSTEM = """Agente SAP SD. Analise o escopo e retorne JSON:
{"entregaveis":[{"mod":"SD","item":"descricao"}],"horas":72,"premissas":["premissa1"],"observacoes":"resumo"}
Inclua: faturamento, NF-e saida, Grupo YA, BAdI NF-e, tpIntegra=1 quando GO/IN1608.
Sem markdown."""

class SDAgent(BaseAgent):
    name = "Sofia (SD)"
    agent_id = "sd"
    def _system_prompt(self): return SYSTEM
