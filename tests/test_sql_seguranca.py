import pytest

from app.core.sql_seguranca import LIMIT_PADRAO, SqlInseguro, validar_e_finalizar_sql


def test_sql_valido_ganha_limit_padrao():
    sql = (
        "SELECT n.id, n.valor_total FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'autorizada'"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert resultado.endswith(f"LIMIT {LIMIT_PADRAO}")


def test_sql_com_limit_ja_presente_nao_duplica():
    sql = (
        "SELECT n.id FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'autorizada' LIMIT 10"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert resultado.count("LIMIT") == 1
    assert resultado.endswith("LIMIT 10")


def test_sql_com_join_em_tabelas_permitidas_passa():
    sql = (
        "SELECT p.nome_canonico, SUM(i.valor_total) FROM notas n "
        "JOIN itens_nota i ON i.nota_id = n.id "
        "JOIN produtos_canonicos p ON p.id = i.produto_canonico_id "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'autorizada' "
        "GROUP BY p.nome_canonico"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert "produtos_canonicos" in resultado


def test_rejeita_notas_sem_mencionar_situacao():
    """situacao decide se nota CANCELADA entra na conta -- exigir a coluna
    explicitamente impede que o SQL gerado ignore isso em silêncio (mesmo
    princípio de exigir :cliente_caso_id)."""
    sql = "SELECT n.id, n.valor_total FROM notas n WHERE n.cliente_caso_id = :cliente_caso_id"
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


def test_aceita_situacao_cancelada_quando_pergunta_pede_explicitamente():
    sql = (
        "SELECT n.id FROM notas n "
        "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'cancelada'"
    )
    resultado = validar_e_finalizar_sql(sql)
    assert "situacao" in resultado.lower()


def test_situacao_nao_e_exigida_sem_a_tabela_notas():
    sql = "SELECT id, nome_canonico FROM produtos_canonicos WHERE cliente_caso_id = :cliente_caso_id"
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


_FILTRO = "WHERE n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'autorizada'"


@pytest.mark.parametrize(
    "sql",
    [
        # join por vírgula: o regex antigo só via a tabela logo após FROM
        f"SELECT u.email, u.hashed_password FROM notas n, usuarios u {_FILTRO}",
        f"SELECT n.id FROM notas n {_FILTRO} AND n.id IN (SELECT id FROM usuarios)",
        f"SELECT n.id FROM notas n {_FILTRO} UNION SELECT hashed_password FROM usuarios",
        f"WITH x AS (SELECT * FROM usuarios) SELECT n.id FROM notas n, x {_FILTRO}",
        f"SELECT n.id FROM notas n, (SELECT email FROM usuarios) x {_FILTRO}",
        f"SELECT n.id FROM notas n JOIN logs_auditoria l ON l.id = n.id {_FILTRO}",
        f"SELECT n.id FROM notas n, mysql.user m {_FILTRO}",
        f"SELECT n.id FROM nfe_sistema.notas n {_FILTRO}",
    ],
)
def test_rejeita_tabela_fora_da_whitelist_em_qualquer_posicao(sql):
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT n.id FROM notas n WHERE n.situacao = 'autorizada' -- :cliente_caso_id",
        f"SELECT n.id FROM notas n {_FILTRO} /* comentario */",
        f"SELECT n.id FROM notas n {_FILTRO} # comentario",
    ],
)
def test_rejeita_comentarios(sql):
    with pytest.raises(SqlInseguro, match="Comentários"):
        validar_e_finalizar_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT SLEEP(10) FROM notas n {_FILTRO}",
        f"SELECT BENCHMARK(100000000, MD5('a')) FROM notas n {_FILTRO}",
        f"SELECT user() FROM notas n {_FILTRO}",
        f"SELECT DATABASE() FROM notas n {_FILTRO}",
        f"SELECT version () FROM notas n {_FILTRO}",
        f"SELECT CURRENT_USER FROM notas n {_FILTRO}",
        f"SELECT @@version FROM notas n {_FILTRO}",
        f"SELECT n.id FROM notas n {_FILTRO} INTO DUMPFILE '/tmp/x'",
        f"SELECT n.id FROM notas n {_FILTRO} INTO OUTFILE '/tmp/x'",
    ],
)
def test_rejeita_funcoes_e_saidas_perigosas(sql):
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


def test_rejeita_limit_acima_do_teto():
    with pytest.raises(SqlInseguro, match="LIMIT"):
        validar_e_finalizar_sql(f"SELECT n.id FROM notas n {_FILTRO} LIMIT 999999")


def test_aceita_limit_no_teto():
    sql = f"SELECT n.id FROM notas n {_FILTRO} LIMIT {LIMIT_PADRAO}"
    assert validar_e_finalizar_sql(sql) == sql


def test_limit_so_na_subquery_ainda_ganha_limit_externo():
    sql = (
        "SELECT i.id FROM itens_nota i WHERE i.nota_id IN "
        f"(SELECT n.id FROM notas n {_FILTRO}) "
    )
    resultado = validar_e_finalizar_sql(sql)
    assert resultado.endswith(f"LIMIT {LIMIT_PADRAO}")


def test_subquery_com_tabelas_permitidas_passa():
    sql = (
        "SELECT COALESCE(SUM(i.quantidade), 0) AS total FROM itens_nota i "
        "WHERE i.produto_canonico_id IN "
        "(SELECT id FROM produtos_canonicos WHERE cliente_caso_id = :cliente_caso_id)"
    )
    assert validar_e_finalizar_sql(sql).endswith(f"LIMIT {LIMIT_PADRAO}")


def test_sql_que_o_parser_nao_entende_e_recusado():
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql("SELECT FROM WHERE :cliente_caso_id (((")


@pytest.mark.parametrize(
    "sql",
    [
        # nome entre crases: invisível para a regex, pego pela árvore
        f"SELECT `sleep`(600) FROM notas n {_FILTRO}",
        f"SELECT `BENCHMARK`(1000000, 1) FROM notas n {_FILTRO}",
        f"SELECT WAIT_FOR_EXECUTED_GTID_SET('x', 600) FROM notas n {_FILTRO}",
        f"SELECT n.id FROM notas n {_FILTRO} LIMIT 10 FOR SHARE",
    ],
)
def test_rejeita_funcao_entre_crases_espera_e_trava(sql):
    with pytest.raises(SqlInseguro):
        validar_e_finalizar_sql(sql)


@pytest.mark.parametrize("limite", ["2.5", "1e3"])
def test_limit_nao_inteiro_e_sql_inseguro_e_nao_erro_500(limite):
    with pytest.raises(SqlInseguro, match="inteiro"):
        validar_e_finalizar_sql(f"SELECT n.id FROM notas n {_FILTRO} LIMIT {limite}")


def test_caracteres_especiais_dentro_de_texto_nao_sao_confundidos_com_sql():
    """`#`, `--`, `@` e palavras proibidas dentro de um literal são dado da
    busca (ex.: lixa nº 80), não comentário nem comando."""
    sql = (
        "SELECT i.descricao_original FROM itens_nota i JOIN notas n ON n.id = i.nota_id "
        f"{_FILTRO} AND i.descricao_original LIKE '%#80%' "
        "AND i.descricao_original NOT LIKE '%--%' AND n.emitente_nome <> 'a@b.com' "
        "AND i.descricao_original NOT LIKE '%INTO%' AND i.descricao_original <> 'x\\'#'"
    )
    assert validar_e_finalizar_sql(sql).startswith(sql)


def test_placeholder_so_dentro_de_texto_nao_conta_como_filtro():
    with pytest.raises(SqlInseguro, match="cliente_caso_id"):
        validar_e_finalizar_sql(
            "SELECT n.id FROM notas n WHERE n.situacao = 'autorizada' "
            "AND n.emitente_nome <> ':cliente_caso_id'"
        )
