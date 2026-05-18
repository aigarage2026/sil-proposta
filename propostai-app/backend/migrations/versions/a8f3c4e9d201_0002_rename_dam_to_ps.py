"""0002 rename proposal_dams → proposal_ps

Renames the DAM (Documento de Arquitetura de Melhoria) artifact to PS
(Proposta de Solução) across schema:

  - Table:  proposal_dams → proposal_ps
  - Column: dam_json     → ps_json
  - Index:  ix_proposal_dams_tenant_id → ix_proposal_ps_tenant_id

Greenfield project — no prod data — but the migration is reversible so it
stays consistent with alembic best practices.

Revision ID: a8f3c4e9d201
Revises: 72c97274bd1e
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a8f3c4e9d201"
down_revision: Union[str, None] = "72c97274bd1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_proposal_dams_tenant_id", table_name="proposal_dams")
    op.alter_column("proposal_dams", "dam_json", new_column_name="ps_json")
    op.rename_table("proposal_dams", "proposal_ps")
    op.create_index(
        "ix_proposal_ps_tenant_id", "proposal_ps", ["tenant_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_proposal_ps_tenant_id", table_name="proposal_ps")
    op.rename_table("proposal_ps", "proposal_dams")
    op.alter_column("proposal_dams", "ps_json", new_column_name="dam_json")
    op.create_index(
        "ix_proposal_dams_tenant_id", "proposal_dams", ["tenant_id"], unique=False,
    )
