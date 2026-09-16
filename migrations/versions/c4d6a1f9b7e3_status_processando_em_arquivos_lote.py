"""status PROCESSANDO em arquivos_lote

Revision ID: c4d6a1f9b7e3
Revises: 8b1e4f6a2c90
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d6a1f9b7e3'
down_revision: Union[str, Sequence[str], None] = '8b1e4f6a2c90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'arquivos_lote',
        'status',
        existing_type=sa.Enum('PENDENTE', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'),
        type_=sa.Enum(
            'PENDENTE', 'PROCESSANDO', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'
        ),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'arquivos_lote',
        'status',
        existing_type=sa.Enum(
            'PENDENTE', 'PROCESSANDO', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'
        ),
        type_=sa.Enum('PENDENTE', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'),
        existing_nullable=True,
    )
