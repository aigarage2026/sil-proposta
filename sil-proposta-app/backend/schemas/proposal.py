"""
Schemas Pydantic para propostas e sub-recursos.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ResourceSchema(BaseModel):
    frente: str
    nivel: str
    dias: int
    horas: int
    cost_rate: Optional[float] = None

    class Config:
        from_attributes = True


class DeliverableSchema(BaseModel):
    module: str
    item: str
    hours: Optional[int] = None
    sort_order: Optional[int] = None

    class Config:
        from_attributes = True


class PremiseSchema(BaseModel):
    text: str
    is_standard: bool = False
    sort_order: Optional[int] = None

    class Config:
        from_attributes = True


class LegislationSchema(BaseModel):
    code: str
    description: Optional[str] = None
    uf: Optional[str] = None
    scope: Optional[str] = None

    class Config:
        from_attributes = True


class ConfidenceSchema(BaseModel):
    escopo: float = 0.0
    horas: float = 0.0
    legislacao: float = 0.0
    comercial: float = 0.0


class AgentExecutionSchema(BaseModel):
    agent_name: str
    status: str
    duration_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    class Config:
        from_attributes = True


class ProposalSummary(BaseModel):
    """Resumo para listagem."""
    id: str
    title: str
    status: str
    project_type: str
    sap_version: str
    states: list[str]
    main_proc: Optional[str] = None
    total_hours: Optional[int] = None
    valor: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProposalDetail(BaseModel):
    """Detalhe completo."""
    id: str
    title: str
    status: str
    project_type: str
    sap_version: str
    states: list[str]
    commercial_model: str
    rfp_text: Optional[str] = None
    new_law: bool = False
    hours_presale: int = 0
    notes: Optional[str] = None
    lang: str = "pt"
    main_proc: Optional[str] = None
    needs_cpi: bool = False
    total_hours: Optional[int] = None
    valor: Optional[float] = None
    generation_mode: Optional[str] = None
    agents_fired: Optional[list[str]] = None
    generation_time_ms: Optional[int] = None
    confidence: ConfidenceSchema = ConfidenceSchema()
    resources: list[ResourceSchema] = []
    deliverables: list[DeliverableSchema] = []
    premises: list[PremiseSchema] = []
    legislations: list[LegislationSchema] = []
    agent_executions: list[AgentExecutionSchema] = []
    dam_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProposalStatusUpdate(BaseModel):
    status: str  # draft, review, approved, won, lost


class ProposalListResponse(BaseModel):
    proposals: list[ProposalSummary]
    total: int
