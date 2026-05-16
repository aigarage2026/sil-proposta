"""
Registro central de modelos SQLAlchemy.
Importar todos os modelos aqui para que Alembic os detecte.
"""
from core.database import Base  # noqa: F401
from models.audit_log import AuditLog  # noqa: F401
from models.company import Company  # noqa: F401
from models.propostai.agent_execution import AgentExecution  # noqa: F401
from models.propostai.knowledge_document import KnowledgeDocument  # noqa: F401

# Domain models (propostai)
from models.propostai.proposal import Proposal  # noqa: F401
from models.propostai.proposal_deliverable import ProposalDeliverable  # noqa: F401
from models.propostai.proposal_legislation import ProposalLegislation  # noqa: F401
from models.propostai.proposal_premise import ProposalPremise  # noqa: F401
from models.propostai.proposal_ps import ProposalPS  # noqa: F401
from models.propostai.proposal_resource import ProposalResource  # noqa: F401
from models.propostai.proposal_template import ProposalTemplate  # noqa: F401

# Base models (agn-core)
from models.tenant import Tenant  # noqa: F401
from models.user import User  # noqa: F401
from models.user_company_access import UserCompanyAccess  # noqa: F401
