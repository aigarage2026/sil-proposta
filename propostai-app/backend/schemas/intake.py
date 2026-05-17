"""
Schemas Pydantic para o intake de propostas (entrada para geração da PS).
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Campos opcionais novos (Onda 5 close): sinal pra Sócrates fazer match
# mais preciso no corpus histórico. Todos opcionais — sem regressão de
# UX pra quem está acostumado com o fluxo atual.
Industry = Literal[
    "varejo", "financeiro", "industrial", "saude", "agro", "publico",
    "logistica", "energia", "telecom", "outro",
]
ProjectSizeHint = Literal["small", "medium", "large", "xl"]
DeadlinePressure = Literal["low", "medium", "high", "critical"]


class IntakePayload(BaseModel):
    """Payload de entrada para gerar uma proposta SAP."""
    company_id: str = Field(..., description="ID da company (cliente final)")
    project_type: str = Field(..., description="ams, new, migration, support")
    sap_version: str = Field(..., description="ecc604, ecc605, s4op, s4cloud")
    states: list[str] = Field(..., min_length=1, description="UFs do cliente")
    commercial_model: str = Field(..., description="fixed, t_m")
    rfp_text: Optional[str] = Field(None, description="Texto da RFP/requisito")
    new_law: bool = Field(False, description="Nova legislacao identificada")
    hours_presale: int = Field(0, ge=0, description="Horas de pre-venda ja gastas")
    notes: Optional[str] = Field(None, description="Observacoes adicionais")
    lang: str = Field("pt", description="Idioma da proposta")
    tax_reform: str = Field("auto", description="Reforma tributaria: yes, no, auto")

    # ── Sócrates matching hints (opcionais) ──────────────────────────────
    industry: Optional[Industry] = Field(
        None,
        description="Setor do cliente final. Sócrates usa pra filtrar matches por indústria.",
    )
    project_size_hint: Optional[ProjectSizeHint] = Field(
        None,
        description="Estimativa grosseira de tamanho. Vazio = Sócrates infere do texto.",
    )
    deadline_pressure: Optional[DeadlinePressure] = Field(
        None,
        description="Pressão de prazo. Afeta calibração e tipo de recurso recomendado.",
    )
    previous_engagement: bool = Field(
        False,
        description="Já fizemos projeto para este cliente antes? Sócrates busca histórico específico.",
    )
