"""
UserCompanyAccess — N:N User <-> Company com role por company.
Owner do tenant NAO precisa desta tabela (acesso implicito a tudo).
"""
from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class UserCompanyAccess(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "user_company_access"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="editor")  # admin, editor, viewer

    # Relationships
    user = relationship("User", back_populates="company_access")
    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_company_access"),
    )
