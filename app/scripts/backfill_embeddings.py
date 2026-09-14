"""
Gera embedding para todo ProdutoCanonico que ainda não tem um, ou que tem um
embedding de um modelo diferente do configurado atualmente
(`embedding IS NULL` ou `embedding_modelo` desatualizado) -- necessário
rodar uma vez por ambiente para os canônicos criados antes do pré-filtro por
embedding existir, e de novo sempre que settings.gemini_embedding_model
mudar (ver app/ai/embeddings.py e
app/workers/tasks.py::normalizar_produtos_pendentes). Canônicos novos já
nascem com embedding do modelo atual, não passam por aqui.

Uso:
    docker compose exec api python -m app.scripts.backfill_embeddings
"""

from sqlalchemy import or_

from app.ai.embeddings import gerar_embeddings, serializar_embedding
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import ProdutoCanonico

_TAMANHO_LOTE = 100


def backfill_embeddings() -> None:
    db = SessionLocal()
    try:
        pendentes = (
            db.query(ProdutoCanonico)
            .filter(
                or_(
                    ProdutoCanonico.embedding.is_(None),
                    ProdutoCanonico.embedding_modelo.is_(None),
                    ProdutoCanonico.embedding_modelo != settings.gemini_embedding_model,
                )
            )
            .all()
        )
        if not pendentes:
            print("Nenhum produto canônico sem embedding atualizado.")
            return

        total = 0
        for i in range(0, len(pendentes), _TAMANHO_LOTE):
            lote = pendentes[i : i + _TAMANHO_LOTE]
            vetores = gerar_embeddings([c.nome_canonico for c in lote])
            for canonico, vetor in zip(lote, vetores):
                canonico.embedding = serializar_embedding(vetor)
                canonico.embedding_modelo = settings.gemini_embedding_model
            db.commit()
            total += len(lote)
            print(f"{total}/{len(pendentes)} produtos canônicos processados.")

        print(f"Concluído: {total} produtos canônicos receberam embedding.")
    finally:
        db.close()


def main() -> None:
    backfill_embeddings()


if __name__ == "__main__":
    main()
