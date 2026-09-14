"""embedding como blob float32 + coluna de modelo

Revision ID: 5f2e9a1c7d34
Revises: e29b41d4a716
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import numpy as np
import sqlalchemy as sa

from app.core.config import settings


# revision identifiers, used by Alembic.
revision: str = '5f2e9a1c7d34'
down_revision: Union[str, Sequence[str], None] = 'e29b41d4a716'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    JSON -> BLOB não é uma troca de tipo em SQL puro (o conteúdo precisa ser
    reescrito, não só o tipo da coluna), então isto adiciona colunas novas,
    copia e converte os dados linha a linha e só então descarta a coluna
    antiga -- preserva os embeddings já calculados em vez de forçar
    reprocessamento via API paga.
    """
    op.add_column('produtos_canonicos', sa.Column('embedding_bin', sa.LargeBinary(), nullable=True))
    op.add_column('produtos_canonicos', sa.Column('embedding_modelo', sa.String(length=120), nullable=True))

    produtos_canonicos = sa.table(
        'produtos_canonicos',
        sa.column('id', sa.Integer),
        sa.column('embedding', sa.JSON),
        sa.column('embedding_bin', sa.LargeBinary),
        sa.column('embedding_modelo', sa.String),
    )

    bind = op.get_bind()
    linhas = bind.execute(
        sa.select(produtos_canonicos.c.id, produtos_canonicos.c.embedding).where(
            produtos_canonicos.c.embedding.isnot(None)
        )
    ).fetchall()
    for id_, vetor in linhas:
        if not vetor:
            continue
        # Assume que todo embedding pré-existente foi gerado com o modelo
        # configurado hoje -- não há, até esta migration, coluna ou registro
        # que indique troca de modelo em algum momento.
        bind.execute(
            produtos_canonicos.update()
            .where(produtos_canonicos.c.id == id_)
            .values(
                embedding_bin=np.asarray(vetor, dtype=np.float32).tobytes(),
                embedding_modelo=settings.gemini_embedding_model,
            )
        )

    op.drop_column('produtos_canonicos', 'embedding')
    op.alter_column(
        'produtos_canonicos',
        'embedding_bin',
        new_column_name='embedding',
        existing_type=sa.LargeBinary(),
    )


def downgrade() -> None:
    """Downgrade schema (best-effort: BLOB float32 -> JSON)."""
    op.add_column('produtos_canonicos', sa.Column('embedding_json', sa.JSON(), nullable=True))

    produtos_canonicos = sa.table(
        'produtos_canonicos',
        sa.column('id', sa.Integer),
        sa.column('embedding', sa.LargeBinary),
        sa.column('embedding_json', sa.JSON),
    )

    bind = op.get_bind()
    linhas = bind.execute(
        sa.select(produtos_canonicos.c.id, produtos_canonicos.c.embedding).where(
            produtos_canonicos.c.embedding.isnot(None)
        )
    ).fetchall()
    for id_, dado in linhas:
        if not dado:
            continue
        bind.execute(
            produtos_canonicos.update()
            .where(produtos_canonicos.c.id == id_)
            .values(embedding_json=np.frombuffer(dado, dtype=np.float32).tolist())
        )

    op.drop_column('produtos_canonicos', 'embedding_modelo')
    op.drop_column('produtos_canonicos', 'embedding')
    op.alter_column(
        'produtos_canonicos',
        'embedding_json',
        new_column_name='embedding',
        existing_type=sa.JSON(),
    )
