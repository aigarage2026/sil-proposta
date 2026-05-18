"""KnowledgeDocument — base de conhecimento para RAG."""
from sqlalchemy import JSON, Boolean, Column, Index, String, Text

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class KnowledgeDocument(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "knowledge_documents"

    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)
    tags = Column(JSON)
    is_global = Column(Boolean, default=False)
    source = Column(String(100))

    __table_args__ = (
        Index("ix_knowledge_tenant_category", "tenant_id", "category"),
    )
