"""Proposal — entidade central do dominio."""
from sqlalchemy import JSON, Boolean, Column, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class Proposal(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "proposals"

    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    title = Column(String(500), nullable=False)
    project_type = Column(String(30), nullable=False)
    sap_version = Column(String(30), nullable=False)
    states = Column(JSON, nullable=False)
    commercial_model = Column(String(30), nullable=False)
    rfp_text = Column(Text)
    new_law = Column(Boolean, default=False)
    hours_presale = Column(Integer, default=0)
    notes = Column(Text)
    lang = Column(String(5), default="pt")

    status = Column(String(30), nullable=False, default="draft")
    main_proc = Column(String(20))
    needs_cpi = Column(Boolean, default=False)
    total_hours = Column(Integer)
    valor = Column(Numeric(12, 2))

    confidence_escopo = Column(Numeric(3, 2))
    confidence_horas = Column(Numeric(3, 2))
    confidence_legislacao = Column(Numeric(3, 2))
    confidence_comercial = Column(Numeric(3, 2))

    generation_mode = Column(String(20))
    agents_fired = Column(JSON)
    generation_time_ms = Column(Integer)

    company = relationship("Company", back_populates="proposals")
    resources = relationship("ProposalResource", back_populates="proposal", cascade="all, delete-orphan")
    deliverables = relationship("ProposalDeliverable", back_populates="proposal", cascade="all, delete-orphan")
    premises = relationship("ProposalPremise", back_populates="proposal", cascade="all, delete-orphan")
    legislations = relationship("ProposalLegislation", back_populates="proposal", cascade="all, delete-orphan")
    dam = relationship("ProposalDam", back_populates="proposal", uselist=False, cascade="all, delete-orphan")
    agent_executions = relationship("AgentExecution", back_populates="proposal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_proposals_tenant_status", "tenant_id", "status"),
        Index("ix_proposals_tenant_company", "tenant_id", "company_id"),
        Index("ix_proposals_tenant_created", "tenant_id", "created_at"),
    )
