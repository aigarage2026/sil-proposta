"""ProposalDam — cache do JSON completo do DAM."""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import UUIDMixin, TimestampMixin, TenantMixin


class ProposalDam(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_dams"

    proposal_id = Column(String(36), ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, unique=True)
    dam_json = Column(JSON, nullable=False)
    version = Column(Integer, default=1)

    proposal = relationship("Proposal", back_populates="dam")
