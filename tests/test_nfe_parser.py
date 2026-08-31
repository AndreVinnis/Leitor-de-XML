from pathlib import Path

from app.parsers.nfe_parser import classificar_tipo, parse_nfe_xml

FIXTURE = Path(__file__).parent / "fixtures" / "nfe_exemplo.xml"


def test_parse_nfe_basico():
    nota = parse_nfe_xml(FIXTURE)

    assert nota.chave_acesso == "35240512345678000199550010000001231234567890"
    assert nota.numero == "123"
    assert nota.emitente_cnpj == "12345678000199"
    assert nota.destinatario_cnpj == "98765432000188"
    assert nota.valor_total == 415
    assert len(nota.itens) == 2

    item1 = nota.itens[0]
    assert item1.descricao_original == "ARROZ TIO JOAO 5KG"
    assert item1.ncm == "10063021"
    assert item1.quantidade == 10
    assert item1.valor_total == 255


def test_classificar_tipo_entrada():
    nota = parse_nfe_xml(FIXTURE)
    assert classificar_tipo(nota, "98765432000188") == "entrada"


def test_classificar_tipo_saida():
    nota = parse_nfe_xml(FIXTURE)
    assert classificar_tipo(nota, "12345678000199") == "saida"
