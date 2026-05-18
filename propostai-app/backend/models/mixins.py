"""
Mixins padrao da plataforma AI Garage (agn-core).
Toda entidade herda UUIDMixin + TimestampMixin.
Entidades com escopo de tenant tambem herdam TenantMixin.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String


class UUIDMixin:
    """Primary key UUID como string."""
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()), nullable=False)


class TimestampMixin:
    """Timestamps automaticos de criacao e atualizacao."""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TenantMixin:
    """Isolamento multi-tenant por row. Todas as queries DEVEM filtrar por tenant_id."""
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
