"""
User — usuario interno do tenant (pre-vendas, gerente, diretor).
Pertence ao Tenant, NAO a uma Company. Acesso a Companies via UserCompanyAccess.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import UUIDMixin, TimestampMixin, TenantMixin


class User(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "users"

    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(255))
    auth_provider = Column(String(20), default="local")  # local, google, linkedin

    # Roles
    role = Column(String(20), nullable=False, default="editor")  # owner, admin, editor, viewer
    is_platform_admin = Column(Boolean, default=False, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime)

    # Preferences
    language = Column(String(5), default="pt")
    avatar_url = Column(String(500))

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    company_access = relationship("UserCompanyAccess", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        # Email unico dentro do tenant
        {"comment": "Constraint de unicidade: tenant_id + email"},
    )
