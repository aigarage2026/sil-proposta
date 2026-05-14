"""ProposalTemplate — template customizavel de proposta."""
from sqlalchemy import Boolean, Column, ForeignKey, JSON, String, UniqueConstraint

from core.database import Base
from models.mixins import UUIDMixin, TimestampMixin, TenantMixin


class ProposalTemplate(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposal_templates"

    company_id = Column(String(36), ForeignKey("companies.id"))
    name = Column(String(200), nullable=False)
    project_type = Column(String(30))
    default_premises = Column(JSON)
    default_resources = Column(JSON)
    branding = Column(JSON)
    is_default = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_template_tenant_name"),
    )
