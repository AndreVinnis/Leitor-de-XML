from unittest.mock import patch

from app.ai.embeddings import serializar_embedding
from app.ai.normalizador_produtos import SugestaoIA
from app.core.config import settings
from app.models.models import ClienteCaso, ItemNota, Nota, ProdutoCanonico, TipoNota
from app.workers.tasks import (
    LIMIAR_FILTRO_EMBEDDING,
    TOP_K_CANDIDATOS,
    normalizar_produtos_pendentes,
)


def _criar_caso(session, nome):
    caso = ClienteCaso(nome_cliente=nome)
    session.add(caso)
    session.commit()
    session.refresh(caso)
    return caso


def _criar_item_pendente(session, caso_id, chave_acesso, descricao):
    nota = Nota(chave_acesso=chave_acesso, tipo=TipoNota.ENTRADA, cliente_caso_id=caso_id)
    session.add(nota)
    session.commit()
    session.refresh(nota)

    item = ItemNota(nota_id=nota.id, descricao_original=descricao)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@patch("app.workers.tasks.sugerir_normalizacao")
def test_canonicos_existentes_nao_vazam_entre_casos(mock_sugerir, db_session_factory):
    """
    O contexto de canônicos enviado à IA para o Caso B não pode incluir
    produtos canônicos criados a partir de dados do Caso A -- catálogo de
    produto é isolado por cliente_caso_id.
    """
    session = db_session_factory()
    caso_a = _criar_caso(session, "Cliente A")
    caso_b = _criar_caso(session, "Cliente B")

    canonico_a = ProdutoCanonico(cliente_caso_id=caso_a.id, nome_canonico="Coca-Cola Lata 350ml")
    session.add(canonico_a)
    session.commit()
    session.refresh(canonico_a)

    _criar_item_pendente(session, caso_b.id, "3" * 44, "COCA COLA 350ML LT")
    session.close()

    mock_sugerir.return_value = [
        SugestaoIA(descricao_original="COCA COLA 350ML LT", confianca=0.9, produto_canonico_id=None)
    ]

    normalizar_produtos_pendentes(caso_b.id)

    # A lista de canônicos existentes passada à IA para o Caso B deve ser
    # vazia -- o canônico do Caso A não pode aparecer como contexto.
    _, canonicos_existentes = mock_sugerir.call_args[0]
    assert canonicos_existentes == []


@patch("app.workers.tasks.sugerir_normalizacao")
def test_produto_canonico_criado_com_caso_correto(mock_sugerir, db_session_factory):
    session = db_session_factory()
    caso = _criar_caso(session, "Cliente C")
    _criar_item_pendente(session, caso.id, "4" * 44, "DETERG NEUTRO 500ML")
    session.close()

    mock_sugerir.return_value = [
        SugestaoIA(
            descricao_original="DETERG NEUTRO 500ML",
            confianca=0.95,
            novo_produto_canonico={"nome_canonico": "Detergente Neutro 500ml", "categoria": "Limpeza"},
        )
    ]

    resultado = normalizar_produtos_pendentes(caso.id)
    assert resultado["produtos_canonicos_criados"] == 1

    session = db_session_factory()
    criado = session.query(ProdutoCanonico).filter_by(nome_canonico="Detergente Neutro 500ml").one()
    assert criado.cliente_caso_id == caso.id


@patch("app.workers.tasks.sugerir_normalizacao")
def test_sem_itens_pendentes_no_caso_nao_chama_ia(mock_sugerir, db_session_factory):
    session = db_session_factory()
    caso_a = _criar_caso(session, "Cliente A")
    caso_b = _criar_caso(session, "Cliente B")
    _criar_item_pendente(session, caso_a.id, "5" * 44, "PARAF M6 20MM ACO INOX")
    session.close()

    resultado = normalizar_produtos_pendentes(caso_b.id)

    assert resultado == {"status": "ok", "descricoes_unicas": 0, "sugestoes_criadas": 0}
    mock_sugerir.assert_not_called()


@patch("app.workers.tasks.sugerir_normalizacao")
def test_catalogo_pequeno_mantem_lista_cheia_sem_prefiltro(mock_sugerir, db_session_factory):
    """
    Catálogo abaixo de LIMIAR_FILTRO_EMBEDDING: comportamento inalterado --
    a lista de canônicos passada à IA continua sendo o catálogo inteiro, sem
    passar pelo pré-filtro de embedding.
    """
    session = db_session_factory()
    caso = _criar_caso(session, "Cliente Pequeno")
    canonico = ProdutoCanonico(cliente_caso_id=caso.id, nome_canonico="Arroz Tio Joao 5kg")
    session.add(canonico)
    session.commit()
    session.refresh(canonico)

    _criar_item_pendente(session, caso.id, "7" * 44, "ARROZ TIO JOAO 5KG")
    session.close()

    mock_sugerir.return_value = [
        SugestaoIA(
            descricao_original="ARROZ TIO JOAO 5KG",
            confianca=0.98,
            produto_canonico_id=canonico.id,
        )
    ]

    normalizar_produtos_pendentes(caso.id)

    _, candidatos = mock_sugerir.call_args[0]
    assert candidatos == [
        {"id": canonico.id, "nome_canonico": "Arroz Tio Joao 5kg", "categoria": None}
    ]


@patch("app.workers.tasks.gerar_embeddings")
@patch("app.workers.tasks.sugerir_normalizacao")
def test_catalogo_grande_usa_prefiltro_de_embedding(mock_sugerir, mock_embeddings, db_session_factory):
    """
    Catálogo acima de LIMIAR_FILTRO_EMBEDDING: a lista de canônicos passada
    à IA deixa de ser o catálogo inteiro e passa a ser só os candidatos mais
    similares (por embedding) à descrição, incluindo o match correto.
    """
    session = db_session_factory()
    caso = _criar_caso(session, "Cliente Grande")

    # LIMIAR_FILTRO_EMBEDDING + 1 canônicos, cada um com um embedding
    # one-hot ortogonal aos demais -- só o "alvo" fica idêntico ao embedding
    # que a descrição vai receber (mockado abaixo).
    total_canonicos = LIMIAR_FILTRO_EMBEDDING + 1
    for i in range(total_canonicos):
        vetor = [0.0] * total_canonicos
        vetor[i] = 1.0
        session.add(
            ProdutoCanonico(
                cliente_caso_id=caso.id,
                nome_canonico=f"Produto {i}",
                embedding=serializar_embedding(vetor),
                embedding_modelo=settings.gemini_embedding_model,
            )
        )
    session.commit()

    alvo = session.query(ProdutoCanonico).filter_by(nome_canonico="Produto 3").one()
    alvo_id = alvo.id

    _criar_item_pendente(session, caso.id, "6" * 44, "DESCRICAO QUALQUER")
    session.close()

    vetor_descricao = [0.0] * total_canonicos
    vetor_descricao[3] = 1.0
    mock_embeddings.return_value = [vetor_descricao]

    mock_sugerir.return_value = [
        SugestaoIA(
            descricao_original="DESCRICAO QUALQUER",
            confianca=0.9,
            produto_canonico_id=alvo_id,
        )
    ]

    resultado = normalizar_produtos_pendentes(caso.id)
    assert resultado["sugestoes_criadas"] == 1

    mock_embeddings.assert_called_once()
    _, candidatos = mock_sugerir.call_args[0]
    ids_candidatos = {c["id"] for c in candidatos}

    assert len(candidatos) <= TOP_K_CANDIDATOS
    assert len(candidatos) < total_canonicos
    assert alvo_id in ids_candidatos
