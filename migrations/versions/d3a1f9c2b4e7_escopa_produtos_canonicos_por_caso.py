"""escopa produtos_canonicos por cliente_caso_id

Revision ID: d3a1f9c2b4e7
Revises: baf1eebe0db2
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a1f9c2b4e7'
down_revision: Union[str, Sequence[str], None] = 'baf1eebe0db2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTA: se este banco já tiver linhas em produtos_canonicos referenciadas
    # por itens de mais de um cliente_caso_id, elas precisam ser duplicadas
    # por caso (e as FKs em itens_nota/sugestoes_normalizacao repontadas)
    # antes de rodar esta migration, já que a coluna abaixo é NOT NULL.
    op.add_column(
        'produtos_canonicos',
        sa.Column('cliente_caso_id', sa.Integer(), nullable=False),
    )
    op.create_index(
        op.f('ix_produtos_canonicos_cliente_caso_id'),
        'produtos_canonicos',
        ['cliente_caso_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_produtos_canonicos_cliente_caso_id_clientes_casos',
        'produtos_canonicos', 'clientes_casos', ['cliente_caso_id'], ['id'],
    )
    op.create_unique_constraint(
        'uq_produto_canonico_caso_nome',
        'produtos_canonicos', ['cliente_caso_id', 'nome_canonico'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_produto_canonico_caso_nome', 'produtos_canonicos', type_='unique')
    op.drop_constraint(
        'fk_produtos_canonicos_cliente_caso_id_clientes_casos',
        'produtos_canonicos', type_='foreignkey',
    )
    op.drop_index(op.f('ix_produtos_canonicos_cliente_caso_id'), table_name='produtos_canonicos')
    op.drop_column('produtos_canonicos', 'cliente_caso_id')
