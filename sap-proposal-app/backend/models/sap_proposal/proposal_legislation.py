"""ProposalLegislation — legislacao fiscal identificada."""
from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import UUIDMixin, TimestampMixin, TenantMixin


class ProposalLegislation(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_legislations"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(100), nullable=False)
    description = Column(Text)
    uf = Column(String(2))
    scope = Column(String(20))

    proposal = relationship("Proposal", back_populates="legislations")
