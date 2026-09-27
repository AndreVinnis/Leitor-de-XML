from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.resposta_consulta import RespostaInvalida, ResultadoSql, montar_resposta


def _resultado(colunas, linhas, finalidade="resposta"):
    return ResultadoSql(finalidade=finalidade, colunas=colunas, linhas=linhas)


def test_formato_numero_inteiro():
    resultados = [_resultado(["total_itens"], [[Decimal("1240")]])]
    texto = montar_resposta("Total: {1.total_itens|numero}.", resultados, "quantos itens?", [])
    assert texto == "Total: 1.240."


def test_formato_numero_com_casas_decimais():
    resultados = [_resultado(["media"], [[Decimal("1240.5")]])]
    texto = montar_resposta("Média: {1.media|numero}.", resultados, "qual a media?", [])
    assert texto == "Média: 1.240,5."


def test_formato_numero_arredonda_sem_deixar_virgula_pendurada():
    # 2.99999 arredonda para 3.0000 na 4ª casa -- não pode sobrar "3,".
    resultados = [_resultado(["v"], [[Decimal("2.99999")]])]
    texto = montar_resposta("{1.v|numero}", resultados, "?", [])
    assert texto == "3"


def test_formato_numero_negativo_proximo_de_zero_nao_vira_menos_zero():
    resultados = [_resultado(["v"], [[Decimal("-0.00001")]])]
    texto = montar_resposta("{1.v|numero}", resultados, "?", [])
    assert texto == "0"


def test_formato_moeda_arredonda_e_usa_padrao_ptbr():
    resultados = [_resultado(["valor"], [[Decimal("18600.005")]])]
    texto = montar_resposta("Total: {1.valor|moeda}.", resultados, "qual o valor?", [])
    assert texto == "Total: R$ 18.600,01."


def test_formato_moeda_com_milhar():
    resultados = [_resultado(["valor"], [[Decimal("3050")]])]
    texto = montar_resposta("Total: {1.valor|moeda}.", resultados, "qual o valor?", [])
    assert texto == "Total: R$ 3.050,00."


def test_formato_moeda_negativa_proxima_de_zero_nao_vira_menos_zero():
    resultados = [_resultado(["v"], [[Decimal("-0.001")]])]
    texto = montar_resposta("{1.v|moeda}", resultados, "?", [])
    assert texto == "R$ 0,00"


def test_formato_data():
    resultados = [_resultado(["data_emissao"], [[date(2026, 4, 15)]])]
    texto = montar_resposta("Emitida em {1.data_emissao|data}.", resultados, "qual data?", [])
    assert texto == "Emitida em 15/04/2026."


def test_formato_data_com_datetime_e_string():
    resultados = [_resultado(["a"], [[datetime(2026, 4, 15, 10, 30)]])]
    texto = montar_resposta("{1.a|data}", resultados, "?", [])
    assert texto == "15/04/2026"

    resultados_str = [_resultado(["a"], [["2026-04-15T10:30:00"]])]
    texto_str = montar_resposta("{1.a|data}", resultados_str, "?", [])
    assert texto_str == "15/04/2026"


def test_data_nula_vira_travessao():
    resultados = [_resultado(["a"], [[None]])]
    texto = montar_resposta("{1.a|data}", resultados, "?", [])
    assert texto == "—"


def test_zero_linhas_na_consulta_resposta_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [])]
    with pytest.raises(RespostaInvalida, match="0 linha"):
        montar_resposta("Total: {1.total|numero} itens.", resultados, "quantos?", [])


def test_mais_de_uma_linha_na_consulta_resposta_levanta_resposta_invalida():
    # Ex.: SQL com GROUP BY que a IA deveria ter escrito sem agrupamento.
    resultados = [_resultado(["tipo", "total"], [["entrada", Decimal("100")], ["saida", Decimal("900")]])]
    with pytest.raises(RespostaInvalida, match="2 linha"):
        montar_resposta("Total: {1.total|moeda}.", resultados, "qual o valor total?", [])


def test_valor_nulo_para_numero_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [[None]])]
    with pytest.raises(RespostaInvalida, match="NULL"):
        montar_resposta("Total: {1.total|numero}.", resultados, "quantos?", [])


def test_valor_nulo_para_moeda_levanta_resposta_invalida():
    resultados = [_resultado(["valor"], [[None]])]
    with pytest.raises(RespostaInvalida, match="NULL"):
        montar_resposta("Total: {1.valor|moeda}.", resultados, "quanto?", [])


def test_marcador_nao_pode_referenciar_consulta_de_fontes():
    resultados = [
        _resultado(["total"], [[Decimal("5")]], finalidade="resposta"),
        _resultado(["nota_id", "valor_total"], [[1, Decimal("5")]], finalidade="fontes"),
    ]
    with pytest.raises(RespostaInvalida, match="finalidade 'fontes'"):
        montar_resposta("Total: {2.valor_total|moeda}.", resultados, "?", [])


def test_marcador_nao_pode_referenciar_consulta_de_listagem():
    resultados = [_resultado(["nota_id"], [[1], [2]], finalidade="listagem")]
    with pytest.raises(RespostaInvalida, match="finalidade 'listagem'"):
        montar_resposta("{1.nota_id|numero}", resultados, "?", [])


def test_coluna_duplicada_levanta_resposta_invalida():
    resultados = [_resultado(["total", "TOTAL"], [[Decimal("1"), Decimal("2")]])]
    with pytest.raises(RespostaInvalida, match="mais de uma vez"):
        montar_resposta("{1.total|numero}", resultados, "?", [])


def test_coluna_e_case_insensitive():
    resultados = [_resultado(["TOTAL_ITENS"], [[Decimal("5")]])]
    texto = montar_resposta("{1.total_itens|numero}", resultados, "?", [])
    assert texto == "5"


def test_referencia_duas_consultas_na_mesma_frase():
    resultados = [
        _resultado(["total_entrada"], [[Decimal("10")]]),
        _resultado(["total_saida"], [[Decimal("20")]]),
    ]
    texto = montar_resposta(
        "Entrada: {1.total_entrada|numero}, saída: {2.total_saida|numero}.",
        resultados,
        "?",
        [],
    )
    assert texto == "Entrada: 10, saída: 20."


def test_marcador_sem_formato_usa_str_para_texto():
    resultados = [_resultado(["nome"], [["Arroz 5kg"]])]
    texto = montar_resposta("Produto: {1.nome}.", resultados, "?", [])
    assert texto == "Produto: Arroz 5kg."


def test_mencao_literal_ao_produto_do_catalogo_e_permitida():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    canonicos = [{"id": 1, "nome_canonico": "Arroz 5kg", "categoria": None}]
    texto = montar_resposta(
        "Sobre o produto Arroz 5kg: {1.total|numero} unidade(s) encontrada(s).",
        resultados,
        "quantos?",
        canonicos,
    )
    assert texto == "Sobre o produto Arroz 5kg: 1 unidade(s) encontrada(s)."


def test_digito_do_catalogo_sem_mencionar_o_produto_por_extenso_e_bloqueado():
    # "5" vem do catálogo ("Arroz 5kg"), mas a frase não cita o produto --
    # o dígito solto não pode ser reaproveitado fora do contexto do produto.
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    canonicos = [{"id": 1, "nome_canonico": "Arroz 5kg", "categoria": None}]
    with pytest.raises(RespostaInvalida, match="número"):
        montar_resposta(
            "Encontrado no pacote de 5kg: {1.total|numero}.", resultados, "quantos?", canonicos
        )


def test_dado_permitido_por_vir_da_pergunta():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    texto = montar_resposta(
        "No mês de 2026: {1.total|numero}.", resultados, "e em 2026?", []
    )
    assert texto == "No mês de 2026: 1."


def test_consulta_inexistente_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    with pytest.raises(RespostaInvalida, match="consulta 2"):
        montar_resposta("{2.total|numero}", resultados, "?", [])


def test_coluna_inexistente_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    with pytest.raises(RespostaInvalida, match="não existe"):
        montar_resposta("{1.outra_coluna|numero}", resultados, "?", [])


def test_formato_desconhecido_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    with pytest.raises(RespostaInvalida, match="[Ff]ormato"):
        montar_resposta("{1.total|percentual}", resultados, "?", [])


def test_numero_inventado_fora_de_marcador_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    with pytest.raises(RespostaInvalida, match="número"):
        montar_resposta(
            "Foram encontrados 128 itens: {1.total|numero}.", resultados, "quantos?", []
        )


def test_numero_por_extenso_fora_de_marcador_nao_e_pego_pela_trava_mas_marcador_continua_a_defesa_principal():
    # A trava de dígito literal não pega numeral por extenso -- é uma rede
    # secundária, documentada como tal; a defesa real é que todo valor
    # variável precisa vir de um marcador (ver docstring do módulo).
    resultados = [_resultado(["total"], [[Decimal("2")]])]
    texto = montar_resposta(
        "Foram encontradas duas notas, somando {1.total|numero}.", resultados, "quantas notas?", []
    )
    assert texto == "Foram encontradas duas notas, somando 2."


def test_modelo_vazio_levanta_resposta_invalida():
    with pytest.raises(RespostaInvalida):
        montar_resposta("", [], "?", [])


def test_marcador_malformado_com_chave_sobrando_levanta_resposta_invalida():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    with pytest.raises(RespostaInvalida, match="chave"):
        montar_resposta("Total: {total}.", resultados, "quantos?", [])


def test_marcador_com_chaves_duplas_deixa_chave_sobrando_e_e_bloqueado():
    resultados = [_resultado(["total"], [[Decimal("1")]])]
    with pytest.raises(RespostaInvalida, match="chave"):
        montar_resposta("{{1.total|numero}}", resultados, "?", [])
