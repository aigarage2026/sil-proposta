"""ProposalResource — recurso alocado no Work Package."""
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import UUIDMixin, TimestampMixin, TenantMixin


class ProposalResource(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_resources"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    frente = Column(String(50), nullable=False)
    nivel = Column(String(30), nullable=False)
    dias = Column(Integer, nullable=False)
    horas = Column(Integer, nullable=False)
    cost_rate = Column(Numeric(8, 2))

    proposal = relationship("Proposal", back_populates="resources")
