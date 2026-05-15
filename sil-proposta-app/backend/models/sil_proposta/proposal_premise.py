"""ProposalPremise — premissa geral ou especifica."""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class ProposalPremise(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_premises"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    is_standard = Column(Boolean, default=False)
    sort_order = Column(Integer)

    proposal = relationship("Proposal", back_populates="premises")
