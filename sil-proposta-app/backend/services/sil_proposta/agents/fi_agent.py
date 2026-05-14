"""Agente FI — Financial Accounting (Felix Inacio)."""
from services.sil_proposta.agents.base_agent import BaseAgent

SYSTEM = """Agente SAP FI. Retorne JSON:
{"entregaveis":[{"mod":"FI","item":"descricao"}],"horas":88,"premissas":["premissa1"],"observacoes":"resumo"}
Inclua: conciliacao bancaria, trigger ECONF, baixa de titulo, contas a receber.
Sem markdown."""

class FIAgent(BaseAgent):
    name = "Felix (FI)"
    agent_id = "fi"
    def _system_prompt(self): return SYSTEM
