from unittest.mock import patch

from app.ai.normalizador_produtos import SugestaoIA
from app.models.models import ClienteCaso, ItemNota, Nota, ProdutoCanonico, TipoNota
from app.workers.tasks import normalizar_produtos_pendentes


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
