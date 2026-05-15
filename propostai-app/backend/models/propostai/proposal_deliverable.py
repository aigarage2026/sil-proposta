"""ProposalDeliverable — entregavel do DAM."""
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class ProposalDeliverable(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_deliverables"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False)
    module = Column(String(20), nullable=False)
    item = Column(String(500), nullable=False)
    hours = Column(Integer)
    sort_order = Column(Integer)

    proposal = relationship("Proposal", back_populates="deliverables")
