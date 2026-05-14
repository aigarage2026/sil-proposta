"""
AuditLog — log de auditoria append-only.
Registra acoes de usuarios para rastreabilidade e compliance.
"""
from sqlalchemy import Column, JSON, String, Text

from core.database import Base
from models.mixins import UUIDMixin, TimestampMixin, TenantMixin


class AuditLog(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "audit_logs"

    user_id = Column(String(36), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    entity = Column(String(100), nullable=False)
    entity_id = Column(String(36))
    changes = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    metadata_ = Column("metadata", JSON)
