"""
Tenant — raiz da multi-tenancy.
Representa uma consultoria SAP cliente da plataforma (ex.: Direto ao Ponto, Accenture SAP).
NAO carrega CNPJ (CNPJ e da Company).
"""
from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TimestampMixin, UUIDMixin


class Tenant(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tenants"

    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    plan_slug = Column(String(50), nullable=False, default="trial")

    # Limites e features
    max_users = Column(Integer, nullable=False, default=5)
    max_proposals_per_month = Column(Integer, nullable=False, default=50)
    max_storage_gb = Column(Integer, nullable=False, default=1)
    features = Column(JSON, default=dict)

    # Branding
    logo_url = Column(String(500))
    primary_color = Column(String(7), default="#3B7BF8")
    branding = Column(JSON, default=dict)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    suspended_at = Column(DateTime)
    suspension_reason = Column(String(500))

    # Preferences
    default_language = Column(String(5), default="pt")
    timezone = Column(String(50), default="America/Sao_Paulo")

    # Relationships
    companies = relationship("Company", back_populates="tenant", cascade="all, delete-orphan")
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
