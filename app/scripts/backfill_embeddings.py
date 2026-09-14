"""
Gera embedding para todo ProdutoCanonico que ainda não tem um
(`embedding IS NULL`) -- necessário rodar uma vez por ambiente para os
canônicos criados antes do pré-filtro por embedding existir (ver
app/ai/embeddings.py e app/workers/tasks.py::normalizar_produtos_pendentes).
Canônicos novos já nascem com embedding, não passam por aqui.

Uso:
    docker compose exec api python -m app.scripts.backfill_embeddings
"""

from app.ai.embeddings import gerar_embeddings
from app.core.database import SessionLocal
from app.models.models import ProdutoCanonico

_TAMANHO_LOTE = 100


def backfill_embeddings() -> None:
    db = SessionLocal()
    try:
        pendentes = db.query(ProdutoCanonico).filter(ProdutoCanonico.embedding.is_(None)).all()
        if not pendentes:
            print("Nenhum produto canônico sem embedding.")
            return

        total = 0
        for i in range(0, len(pendentes), _TAMANHO_LOTE):
            lote = pendentes[i : i + _TAMANHO_LOTE]
            vetores = gerar_embeddings([c.nome_canonico for c in lote])
            for canonico, vetor in zip(lote, vetores):
                canonico.embedding = vetor
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
