import pytest

from app.core.sql_seguranca import LIMIT_PADRAO, SqlInseguro, validar_e_finalizar_sql


def test_sql_valido_ganha_limit_padrao():
    sql = (
        "SELECT n.id, n.valor_total FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert resultado.endswith(f"LIMIT {LIMIT_PADRAO}")


def test_sql_com_limit_ja_presente_nao_duplica():
    sql = (
        "SELECT n.id FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id LIMIT 10"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert resultado.count("LIMIT") == 1
    assert resultado.endswith("LIMIT 10")


def test_sql_com_join_em_tabelas_permitidas_passa():
    sql = (
        "SELECT p.nome_canonico, SUM(i.valor_total) FROM notas n "
        "JOIN itens_nota i ON i.nota_id = n.id "
        "JOIN produtos_canonicos p ON p.id = i.produto_canonico_id "
        "WHERE n.cliente_caso_id = :cliente_caso_id "
        "GROUP BY p.nome_canonico"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert "produtos_canonicos" in resultado


def test_rejeita_mais_de_um_comando():
    sql = "SELECT * FROM notas WHERE cliente_caso_id = :cliente_caso_id; DROP TABLE notas"
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


def test_rejeita_tabela_fora_da_whitelist():
    sql = "SELECT * FROM usuarios WHERE cliente_caso_id = :cliente_caso_id"
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


def test_rejeita_palavra_chave_proibida():
    sql = "SELECT * FROM notas WHERE cliente_caso_id = :cliente_caso_id AND 1=1; INSERT INTO notas VALUES (1)"
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


def test_rejeita_sem_placeholder_cliente_caso_id():
    sql = "SELECT * FROM notas WHERE cliente_caso_id = 1"
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


def test_rejeita_comando_que_nao_e_select():
    sql = "UPDATE notas SET valor_total = 0 WHERE cliente_caso_id = :cliente_caso_id"
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)
