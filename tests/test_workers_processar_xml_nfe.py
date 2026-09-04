from app.models.models import (
    ArquivoLote,
    ClienteCaso,
    Lote,
    RoleUsuario,
    StatusCadastro,
    StatusProcessamento,
    Usuario,
)
from app.workers.tasks import processar_xml_nfe

XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide>
        <nNF>1</nNF>
        <serie>1</serie>
        <dhEmi>2024-05-10T14:32:10-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12345678000199</CNPJ>
        <xNome>FORNECEDOR EXEMPLO LTDA</xNome>
      </emit>
      <dest>
        <CNPJ>98765432000188</CNPJ>
        <xNome>CLIENTE EXEMPLO LTDA</xNome>
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
</nfeProc>"""

CNPJ_CLIENTE = "98765432000188"


def _criar_caso(session, nome="Cliente Teste"):
    caso = ClienteCaso(nome_cliente=nome)
    session.add(caso)
    session.commit()
    session.refresh(caso)
    return caso


def _criar_usuario(session, email="adv@x.com"):
    usuario = Usuario(
        nome="Advogada",
        email=email,
        hashed_password="x",
        role=RoleUsuario.COMUM,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    return usuario


def _criar_lote(session, caso_id, usuario_id, lote_id):
    lote = Lote(
        id=lote_id,
        cliente_caso_id=caso_id,
        cnpj_cliente=CNPJ_CLIENTE,
        total_arquivos=1,
        criado_por_usuario_id=usuario_id,
    )
    session.add(lote)
    session.commit()
    session.refresh(lote)
    return lote


def _criar_arquivo_lote(session, lote_id, nome_arquivo="nota.xml"):
    arquivo = ArquivoLote(
        lote_id=lote_id, nome_arquivo=nome_arquivo, status=StatusProcessamento.PENDENTE
    )
    session.add(arquivo)
    session.commit()
    session.refresh(arquivo)
    return arquivo


def test_processar_xml_sucesso_marca_arquivo_lote_e_grava_nota_id(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-sucesso")
    arquivo_lote = _criar_arquivo_lote(session, lote.id)
    session.close()

    xml_path = tmp_path / "nota.xml"
    xml_path.write_text(XML_TEMPLATE.format(chave="1" * 44), encoding="utf-8")

    resultado = processar_xml_nfe(str(xml_path), CNPJ_CLIENTE, caso.id, arquivo_lote.id)
    assert resultado["status"] == "ok"

    session = db_session_factory()
    atualizado = session.get(ArquivoLote, arquivo_lote.id)
    assert atualizado.status == StatusProcessamento.SUCESSO
    assert atualizado.nota_id is not None
    assert atualizado.motivo_erro is None


def test_processar_xml_duplicado_marca_arquivo_lote(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-duplicado")
    arquivo_lote_1 = _criar_arquivo_lote(session, lote.id, "nota1.xml")
    arquivo_lote_2 = _criar_arquivo_lote(session, lote.id, "nota2.xml")
    session.close()

    xml_path = tmp_path / "nota.xml"
    xml_path.write_text(XML_TEMPLATE.format(chave="2" * 44), encoding="utf-8")

    processar_xml_nfe(str(xml_path), CNPJ_CLIENTE, caso.id, arquivo_lote_1.id)
    resultado_2 = processar_xml_nfe(str(xml_path), CNPJ_CLIENTE, caso.id, arquivo_lote_2.id)
    assert resultado_2["status"] == "ja_existente"

    session = db_session_factory()
    primeiro = session.get(ArquivoLote, arquivo_lote_1.id)
    segundo = session.get(ArquivoLote, arquivo_lote_2.id)
    assert primeiro.status == StatusProcessamento.SUCESSO
    assert segundo.status == StatusProcessamento.DUPLICADO


def test_processar_xml_malformado_marca_erro_com_motivo(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-erro")
    arquivo_lote = _criar_arquivo_lote(session, lote.id, "malformado.xml")
    session.close()

    xml_path = tmp_path / "malformado.xml"
    xml_path.write_text("<nfeProc><NFe><infNFe>", encoding="utf-8")  # XML malformado (não fecha)

    resultado = processar_xml_nfe(str(xml_path), CNPJ_CLIENTE, caso.id, arquivo_lote.id)
    assert resultado["status"] == "erro"

    session = db_session_factory()
    atualizado = session.get(ArquivoLote, arquivo_lote.id)
    assert atualizado.status == StatusProcessamento.ERRO
    assert atualizado.motivo_erro is not None
    assert atualizado.nota_id is None
