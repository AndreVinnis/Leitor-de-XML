"""cnpj_cliente em clientes_casos

Revision ID: 8b1e4f6a2c90
Revises: 5f2e9a1c7d34
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b1e4f6a2c90'
down_revision: Union[str, Sequence[str], None] = '5f2e9a1c7d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('clientes_casos', sa.Column('cnpj_cliente', sa.String(length=14), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clientes_casos', 'cnpj_cliente')
