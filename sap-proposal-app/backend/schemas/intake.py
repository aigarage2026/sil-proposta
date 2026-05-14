"""
Schemas Pydantic para o intake de propostas.
"""
from typing import Optional
from pydantic import BaseModel, Field


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
