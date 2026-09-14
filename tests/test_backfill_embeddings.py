from app.ai.embeddings import serializar_embedding
from app.core.config import settings
from app.models.models import ClienteCaso, ProdutoCanonico
from app.scripts.backfill_embeddings import backfill_embeddings


def _criar_caso(session, nome="Cliente Backfill"):
    caso = ClienteCaso(nome_cliente=nome)
    session.add(caso)
    session.commit()
    session.refresh(caso)
    return caso


def test_backfill_gera_embedding_so_para_quem_nao_tem(db_session_factory):
    session = db_session_factory()
    caso = _criar_caso(session)
    sem_embedding = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Produto Sem Embedding")
    com_embedding = ProdutoCanonico(
        cliente_caso_id=caso.id,
        nome_canonico="Produto Com Embedding",
        embedding=serializar_embedding([9.0, 9.0]),
        embedding_modelo=settings.gemini_embedding_model,
    )
    session.add_all([sem_embedding, com_embedding])
    session.commit()
    session.refresh(sem_embedding)
    session.refresh(com_embedding)
    session.close()

    backfill_embeddings()

    session = db_session_factory()
    atualizado = session.get(ProdutoCanonico, sem_embedding.id)
    inalterado = session.get(ProdutoCanonico, com_embedding.id)
    assert atualizado.embedding is not None
    assert atualizado.embedding_modelo == settings.gemini_embedding_model
    assert inalterado.embedding == serializar_embedding([9.0, 9.0])
    session.close()


def test_backfill_regenera_embedding_de_modelo_desatualizado(db_session_factory):
    session = db_session_factory()
    caso = _criar_caso(session, "Cliente Backfill Modelo Antigo")
    desatualizado = ProdutoCanonico(
        cliente_caso_id=caso.id,
        nome_canonico="Produto Modelo Antigo",
        embedding=serializar_embedding([1.0, 2.0]),
        embedding_modelo="modelo-antigo-000",
    )
    session.add(desatualizado)
    session.commit()
    session.refresh(desatualizado)
    session.close()

    backfill_embeddings()

    session = db_session_factory()
    atualizado = session.get(ProdutoCanonico, desatualizado.id)
    assert atualizado.embedding_modelo == settings.gemini_embedding_model
    assert atualizado.embedding != serializar_embedding([1.0, 2.0])
    session.close()


def test_backfill_sem_pendentes_nao_quebra(db_session_factory):
    db_session_factory()
    backfill_embeddings()
