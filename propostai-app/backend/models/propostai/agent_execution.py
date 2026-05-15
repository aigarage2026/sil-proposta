"""AgentExecution — log de execucao de cada agente IA."""
from sqlalchemy import JSON, Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class AgentExecution(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "agent_executions"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    duration_ms = Column(Integer)
    result_json = Column(JSON)
    error_message = Column(Text)

    proposal = relationship("Proposal", back_populates="agent_executions")

    __table_args__ = (
        Index("ix_agent_exec_proposal", "proposal_id", "agent_name"),
    )
