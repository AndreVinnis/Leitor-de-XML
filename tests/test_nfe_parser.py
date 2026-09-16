from pathlib import Path

from app.parsers.nfe_parser import NFeParseError, classificar_tipo, parse_nfe_xml

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


def test_parse_bloqueia_entidade_externa_xxe(tmp_path):
    """XML com DOCTYPE/ENTITY tentando ler um arquivo local (XXE) não deve
    vazar o conteúdo desse arquivo para o resultado do parsing."""
    segredo = tmp_path / "segredo.txt"
    segredo.write_text("CONTEUDO_SECRETO_XXE")

    xml_malicioso = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE nfeProc [
  <!ENTITY xxe SYSTEM "file://{segredo.as_posix()}">
]>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe35240512345678000199550010000001231234567890" versao="4.00">
      <ide>
        <nNF>123</nNF>
        <serie>1</serie>
        <dhEmi>2024-05-10T14:32:10-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12345678000199</CNPJ>
        <xNome>FORNECEDOR EXEMPLO LTDA</xNome>
      </emit>
      <dest>
        <CNPJ>98765432000188</CNPJ>
        <xNome>&xxe;</xNome>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>001</cProd>
          <xProd>ARROZ TIO JOAO 5KG</xProd>
          <NCM>10063021</NCM>
          <CFOP>5102</CFOP>
          <uCom>UN</uCom>
          <qCom>10.0000</qCom>
          <vUnCom>25.5000</vUnCom>
          <vProd>255.00</vProd>
        </prod>
      </det>
      <total>
        <ICMSTot>
          <vNF>255.00</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
"""
    xml_path = tmp_path / "malicioso.xml"
    xml_path.write_text(xml_malicioso, encoding="utf-8")

    try:
        nota = parse_nfe_xml(xml_path)
    except NFeParseError:
        return  # bloquear com erro de parsing também é um resultado aceitável

    campos = [nota.destinatario_nome, nota.emitente_nome, nota.numero, nota.serie]
    assert all(campo is None or "CONTEUDO_SECRETO_XXE" not in campo for campo in campos)
