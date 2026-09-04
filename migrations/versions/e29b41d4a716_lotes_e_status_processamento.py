"""lotes e status de processamento

Revision ID: e29b41d4a716
Revises: d3a1f9c2b4e7
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e29b41d4a716'
down_revision: Union[str, Sequence[str], None] = 'd3a1f9c2b4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'lotes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('cliente_caso_id', sa.Integer(), nullable=False),
        sa.Column('cnpj_cliente', sa.String(length=14), nullable=False),
        sa.Column('total_arquivos', sa.Integer(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['cliente_caso_id'], ['clientes_casos.id'], ),
        sa.ForeignKeyConstraint(['criado_por_usuario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lotes_cliente_caso_id'), 'lotes', ['cliente_caso_id'], unique=False)

    op.create_table(
        'arquivos_lote',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lote_id', sa.String(length=36), nullable=False),
        sa.Column('nome_arquivo', sa.String(length=500), nullable=False),
        sa.Column('task_id', sa.String(length=155), nullable=True),
        sa.Column(
            'status',
            sa.Enum('PENDENTE', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'),
            nullable=True,
        ),
        sa.Column('motivo_erro', sa.Text(), nullable=True),
        sa.Column('nota_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['lote_id'], ['lotes.id'], ),
        sa.ForeignKeyConstraint(['nota_id'], ['notas.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_arquivos_lote_lote_id'), 'arquivos_lote', ['lote_id'], unique=False)
    op.create_index(op.f('ix_arquivos_lote_nota_id'), 'arquivos_lote', ['nota_id'], unique=False)
    op.create_index(op.f('ix_arquivos_lote_status'), 'arquivos_lote', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_arquivos_lote_status'), table_name='arquivos_lote')
    op.drop_index(op.f('ix_arquivos_lote_nota_id'), table_name='arquivos_lote')
    op.drop_index(op.f('ix_arquivos_lote_lote_id'), table_name='arquivos_lote')
    op.drop_table('arquivos_lote')
    op.drop_index(op.f('ix_lotes_cliente_caso_id'), table_name='lotes')
    op.drop_table('lotes')
