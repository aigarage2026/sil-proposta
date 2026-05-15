"""
Registro central de modelos SQLAlchemy.
Importar todos os modelos aqui para que Alembic os detecte.
"""
from core.database import Base  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
from models.company import Company  # noqa: F401
from models.sil_proposta.agent_execution import AgentExecution  # noqa: F401
from models.sil_proposta.knowledge_document import KnowledgeDocument  # noqa: F401

# Domain models (sil_proposta)
from models.sil_proposta.proposal import Proposal  # noqa: F401
from models.sil_proposta.proposal_dam import ProposalDam  # noqa: F401
from models.sil_proposta.proposal_deliverable import ProposalDeliverable  # noqa: F401
from models.sil_proposta.proposal_legislation import ProposalLegislation  # noqa: F401
from models.sil_proposta.proposal_premise import ProposalPremise  # noqa: F401
from models.sil_proposta.proposal_resource import ProposalResource  # noqa: F401
from models.sil_proposta.proposal_template import ProposalTemplate  # noqa: F401

# Base models (agn-core)
from models.tenant import Tenant  # noqa: F401
from models.user import User  # noqa: F401
from models.user_company_access import UserCompanyAccess  # noqa: F401
