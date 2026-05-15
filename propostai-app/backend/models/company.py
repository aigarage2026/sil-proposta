"""
Company — cliente final da consultoria SAP (CNPJ, razao social).
Sempre vinculada a um Tenant. Propostas sao filhas da Company.
"""
from sqlalchemy import JSON, Boolean, Column, String
from sqlalchemy.orm import relationship

from core.database import Base
from models.mixins import TenantMixin, TimestampMixin, UUIDMixin


class Company(Base, UUIDMixin, TimestampMixin, TenantMixin):
    __tablename__ = "companies"

    name = Column(String(255), nullable=False)
    cnpj = Column(String(18))  # NULL ate wizard completar
    razao_social = Column(String(500))
    is_default = Column(Boolean, default=False, nullable=False)

    # SAP Environment
    sap_version = Column(String(30))  # ecc604, ecc605, s4op, s4cloud
    sap_modules = Column(JSON, default=list)
    states = Column(JSON, default=list)  # UFs do cliente

    # Contact
    contact_name = Column(String(255))
    contact_email = Column(String(255))
    contact_phone = Column(String(30))

    # Metadata
    notes = Column(String(1000))
    tags = Column(JSON, default=list)

    # Relationships
    tenant = relationship("Tenant", back_populates="companies")
    proposals = relationship("Proposal", back_populates="company", cascade="all, delete-orphan")
