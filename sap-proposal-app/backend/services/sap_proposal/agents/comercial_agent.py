"""Agente Comercial (Camila Oliveira)."""
from services.sap_proposal.agents.base_agent import BaseAgent

SYSTEM = """Agente Comercial. Padrao Cast Group: valor fechado, 50%/50%, garantia 30d, validade 30d.
Retorne JSON:
{"faturamento":"50%/50%","garantia":"30 dias","validade":"30 dias",
 "valor_referencia":0,
 "premissas":["Esta proposta nao contempla a extracao dos dados da maquininha.",
              "Todos os desenvolvimentos em ABAP.","Gerenciamento remoto durante toda a execucao."]}
Sem markdown."""

class ComercialAgent(BaseAgent):
    name = "Camila (Comercial)"
    agent_id = "com"
    def _system_prompt(self): return SYSTEM
