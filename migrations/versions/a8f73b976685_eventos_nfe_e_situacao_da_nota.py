"""eventos_nfe e situacao da nota

Revision ID: a8f73b976685
Revises: c4d6a1f9b7e3
Create Date: 2026-09-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8f73b976685'
down_revision: Union[str, Sequence[str], None] = 'c4d6a1f9b7e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'arquivos_lote',
        'status',
        existing_type=sa.Enum(
            'PENDENTE', 'PROCESSANDO', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'
        ),
        type_=sa.Enum(
            'PENDENTE', 'PROCESSANDO', 'SUCESSO', 'ERRO', 'DUPLICADO', 'EVENTO',
            name='statusprocessamento',
        ),
        existing_nullable=True,
    )

    # nullable=True na criação porque a tabela já tem dados -- backfill logo
    # abaixo, depois vira NOT NULL.
    op.add_column(
        'notas',
        sa.Column('situacao', sa.Enum('AUTORIZADA', 'CANCELADA', name='situacaonota'), nullable=True),
    )
    op.add_column('notas', sa.Column('cancelada_em', sa.DateTime(), nullable=True))

    op.execute("UPDATE notas SET situacao = 'AUTORIZADA' WHERE situacao IS NULL")

    op.alter_column(
        'notas',
        'situacao',
        existing_type=sa.Enum('AUTORIZADA', 'CANCELADA', name='situacaonota'),
        nullable=False,
    )
    op.create_index(op.f('ix_notas_situacao'), 'notas', ['situacao'], unique=False)

    op.create_table(
        'eventos_nfe',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cliente_caso_id', sa.Integer(), nullable=False),
        sa.Column('chave_acesso', sa.String(length=44), nullable=False),
        sa.Column('tipo_evento', sa.String(length=6), nullable=False),
        sa.Column('numero_sequencia', sa.Integer(), nullable=False),
        sa.Column('descricao_evento', sa.String(length=255), nullable=True),
        sa.Column('data_evento', sa.DateTime(), nullable=True),
        sa.Column('justificativa', sa.Text(), nullable=True),
        sa.Column('tp_amb', sa.String(length=1), nullable=True),
        sa.Column('protocolo', sa.String(length=20), nullable=True),
        sa.Column('cstat', sa.String(length=3), nullable=False),
        sa.Column('motivo', sa.String(length=255), nullable=True),
        sa.Column('nota_id', sa.Integer(), nullable=True),
        sa.Column('arquivo_lote_id', sa.Integer(), nullable=True),
        sa.Column('aplicado', sa.Boolean(), nullable=False),
        sa.Column('arquivo_origem', sa.String(length=500), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['cliente_caso_id'], ['clientes_casos.id'], ),
        sa.ForeignKeyConstraint(['nota_id'], ['notas.id'], ),
        sa.ForeignKeyConstraint(['arquivo_lote_id'], ['arquivos_lote.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'cliente_caso_id', 'chave_acesso', 'tipo_evento', 'numero_sequencia', 'cstat',
            name='uq_evento_caso_chave_tipo_seq_cstat',
        ),
    )
    op.create_index(
        op.f('ix_eventos_nfe_cliente_caso_id'), 'eventos_nfe', ['cliente_caso_id'], unique=False
    )
    op.create_index(
        op.f('ix_eventos_nfe_chave_acesso'), 'eventos_nfe', ['chave_acesso'], unique=False
    )
    op.create_index(
        op.f('ix_eventos_nfe_tipo_evento'), 'eventos_nfe', ['tipo_evento'], unique=False
    )
    op.create_index(op.f('ix_eventos_nfe_nota_id'), 'eventos_nfe', ['nota_id'], unique=False)
    op.create_index(op.f('ix_eventos_nfe_aplicado'), 'eventos_nfe', ['aplicado'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # DROP TABLE sozinho já remove os índices e as FKs junto -- dropar os
    # índices de nota_id/cliente_caso_id antes falha no MySQL/InnoDB
    # ("Cannot drop index: needed in a foreign key constraint"), porque cada
    # um é o único índice que sustenta a FK correspondente.
    op.drop_table('eventos_nfe')

    op.drop_index(op.f('ix_notas_situacao'), table_name='notas')
    op.drop_column('notas', 'cancelada_em')
    op.drop_column('notas', 'situacao')

    # Sem isso, o ALTER COLUMN abaixo falha com "Data truncated for column
    # 'status'" (sql_mode inclui STRICT_TRANS_TABLES) assim que existir uma
    # linha EVENTO -- e como DDL não é transacional no MySQL, o DROP TABLE e
    # os DROP COLUMN acima já teriam sido aplicados, deixando o schema pela
    # metade e sem caminho de volta. Rebaixa para ERRO (mais neutro que
    # inventar um SUCESSO para arquivo que nunca foi uma nota).
    op.execute("UPDATE arquivos_lote SET status = 'ERRO' WHERE status = 'EVENTO'")

    op.alter_column(
        'arquivos_lote',
        'status',
        existing_type=sa.Enum(
            'PENDENTE', 'PROCESSANDO', 'SUCESSO', 'ERRO', 'DUPLICADO', 'EVENTO',
            name='statusprocessamento',
        ),
        type_=sa.Enum(
            'PENDENTE', 'PROCESSANDO', 'SUCESSO', 'ERRO', 'DUPLICADO', name='statusprocessamento'
        ),
        existing_nullable=True,
    )
