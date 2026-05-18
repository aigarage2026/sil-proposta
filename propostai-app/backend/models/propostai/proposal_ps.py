"""ProposalPS — cache do JSON completo da PS (Proposta de Solução)."""
from sqlalchemy import JSON, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class ProposalPS(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_ps"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, unique=True)
    ps_json = Column(JSON, nullable=False)
    version = Column(Integer, default=1)

    proposal = relationship("Proposal", back_populates="ps")
