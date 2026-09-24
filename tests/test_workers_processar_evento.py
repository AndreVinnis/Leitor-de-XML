from unittest.mock import MagicMock

from app.models.models import (
    ArquivoLote,
    ClienteCaso,
    EventoNFe,
    Lote,
    Nota,
    RoleUsuario,
    SituacaoNota,
    StatusCadastro,
    StatusProcessamento,
    Usuario,
)
from app.workers import tasks as tasks_module
from app.workers.tasks import aplicar_eventos_pendentes, processar_xml_nfe

CNPJ_CLIENTE = "98765432000188"
CHAVE = "9" * 44

XML_NOTA_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
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


def _xml_evento_cancelamento(chave, *, n_seq=1, cstat="135", tp_amb="1", com_ret_evento=True):
    ret_evento = ""
    if com_ret_evento:
        ret_evento = f"""
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>{tp_amb}</tpAmb>
      <cStat>{cstat}</cStat>
      <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
      <chNFe>{chave}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>{n_seq}</nSeqEvento>
      <nProt>135240000000{n_seq:03d}</nProt>
    </infEvento>
  </retEvento>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011135{chave[2:]}{n_seq:03d}">
      <tpAmb>{tp_amb}</tpAmb>
      <chNFe>{chave}</chNFe>
      <dhEvento>2024-05-15T10:00:00-03:00</dhEvento>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>{n_seq}</nSeqEvento>
      <detEvento versao="1.00">
        <descEvento>Cancelamento</descEvento>
        <xJust>Erro na emissao</xJust>
      </detEvento>
    </infEvento>
  </evento>{ret_evento}
</procEventoNFe>
"""


def _xml_evento_nao_cancelamento(chave, tipo_evento="210200"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID{tipo_evento}35{chave[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{chave}</chNFe>
      <dhEvento>2024-05-15T10:00:00-03:00</dhEvento>
      <tpEvento>{tipo_evento}</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00">
        <descEvento>Manifestacao</descEvento>
      </detEvento>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>1</tpAmb>
      <cStat>135</cStat>
      <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
      <chNFe>{chave}</chNFe>
      <tpEvento>{tipo_evento}</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <nProt>135240000000999</nProt>
    </infEvento>
  </retEvento>
</procEventoNFe>
"""


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


def _criar_arquivo_lote(session, lote_id, nome_arquivo="arquivo.xml"):
    arquivo = ArquivoLote(
        lote_id=lote_id, nome_arquivo=nome_arquivo, status=StatusProcessamento.PENDENTE
    )
    session.add(arquivo)
    session.commit()
    session.refresh(arquivo)
    return arquivo


def test_cancelamento_sobre_nota_existente_marca_cancelada(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-cancelamento")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    resultado_nota = processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)
    assert resultado_nota["status"] == "ok"

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")
    resultado_evento = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)
    assert resultado_evento["status"] == "evento"

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.CANCELADA
    assert nota.cancelada_em is not None

    arquivo_evento_atualizado = session.get(ArquivoLote, arquivo_evento.id)
    assert arquivo_evento_atualizado.status == StatusProcessamento.EVENTO
    assert arquivo_evento_atualizado.nota_id is None  # nunca preenchido para evento

    evento = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).one()
    assert evento.aplicado is True
    assert evento.nota_id == nota.id
    assert evento.arquivo_lote_id == arquivo_evento.id


def test_evento_orfao_e_aplicado_quando_nota_chega_depois(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-orfao")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    session.close()

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")
    resultado_evento = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)
    assert resultado_evento["status"] == "evento"

    session = db_session_factory()
    evento_orfao = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).one()
    assert evento_orfao.nota_id is None
    assert evento_orfao.aplicado is False
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    resultado_nota = processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)
    assert resultado_nota["status"] == "ok"

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.CANCELADA

    evento_aplicado = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).one()
    assert evento_aplicado.aplicado is True
    assert evento_aplicado.nota_id == nota.id


def test_evento_repetido_vira_duplicado_e_ainda_aplica_pendente(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-evento-duplicado")
    arquivo_evento_1 = _criar_arquivo_lote(session, lote.id, "evento1.xml")
    arquivo_evento_2 = _criar_arquivo_lote(session, lote.id, "evento2.xml")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    session.close()

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")

    resultado_1 = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento_1.id)
    assert resultado_1["status"] == "evento"
    resultado_2 = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento_2.id)
    assert resultado_2["status"] == "ja_existente"

    session = db_session_factory()
    eventos = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).all()
    assert len(eventos) == 1  # não duplicou a linha

    arquivo_2 = session.get(ArquivoLote, arquivo_evento_2.id)
    assert arquivo_2.status == StatusProcessamento.DUPLICADO
    session.close()

    # a nota chega depois do reupload duplicado -- o cancelamento ainda
    # precisa ser aplicado.
    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.CANCELADA


def test_nota_reprocessada_ja_existente_aplica_evento_pendente(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-reprocessa")
    arquivo_nota_1 = _criar_arquivo_lote(session, lote.id, "nota1.xml")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    arquivo_nota_2 = _criar_arquivo_lote(session, lote.id, "nota2.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota_1.id)

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)

    # simula um retry do Celery reprocessando a mesma nota (cai em ja_existente)
    resultado = processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota_2.id)
    assert resultado["status"] == "ja_existente"

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.CANCELADA


def test_evento_nao_cancelamento_nao_toca_na_nota(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-nao-cancelamento")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_nao_cancelamento(CHAVE), encoding="utf-8")
    resultado = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)
    assert resultado["status"] == "evento"

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.AUTORIZADA

    evento = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).one()
    assert evento.nota_id == nota.id
    assert evento.aplicado is True  # aplicado = tentativa concluída, não = cancelou


def test_evento_sem_ret_evento_nao_cancela(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-sem-ret-evento")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE, com_ret_evento=False), encoding="utf-8")
    resultado = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)
    assert resultado["status"] == "evento"

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.AUTORIZADA

    evento = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).one()
    # Nunca None -- ver comentário em EventoNFe.cstat sobre UNIQUE com NULL.
    assert evento.cstat == ""
    assert evento.aplicado is True


def test_evento_cstat_rejeitado_nao_cancela(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-cstat-rejeitado")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE, cstat="573"), encoding="utf-8")
    processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.AUTORIZADA


def test_evento_de_outro_caso_nao_atinge_a_nota(db_session_factory, tmp_path):
    session = db_session_factory()
    caso_a = _criar_caso(session, "Caso A")
    caso_b = _criar_caso(session, "Caso B")
    usuario = _criar_usuario(session)
    lote_a = _criar_lote(session, caso_a.id, usuario.id, "lote-caso-a")
    lote_b = _criar_lote(session, caso_b.id, usuario.id, "lote-caso-b")
    arquivo_nota = _criar_arquivo_lote(session, lote_a.id, "nota.xml")
    arquivo_evento = _criar_arquivo_lote(session, lote_b.id, "evento.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso_a.id, arquivo_nota.id)

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")
    # mesma chave, mas enfileirado com o cliente_caso_id do caso B
    processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso_b.id, arquivo_evento.id)

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.AUTORIZADA  # não foi cancelada pelo evento do outro caso

    evento = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).one()
    assert evento.nota_id is None  # nunca achou nota nesse caso


def test_mesmo_evento_em_dois_casos_nao_colide_na_unique(db_session_factory, tmp_path):
    """A UNIQUE de EventoNFe inclui cliente_caso_id -- sem isso, o mesmo XML
    de evento (mesma chave/tipo/sequência/cstat), subido por engano em dois
    casos onde a nota não existe em nenhum dos dois (órfão nos dois),
    colidiria na constraint: o segundo caso leria/"aplicaria pendente" a
    linha do primeiro em vez de ganhar a sua própria. chave_acesso de Nota é
    UNIQUE global, por isso o teste usa órfão nos dois casos em vez de criar
    a mesma nota duas vezes."""
    session = db_session_factory()
    caso_a = _criar_caso(session, "Caso A")
    caso_b = _criar_caso(session, "Caso B")
    usuario = _criar_usuario(session)
    lote_a = _criar_lote(session, caso_a.id, usuario.id, "lote-dois-casos-a")
    lote_b = _criar_lote(session, caso_b.id, usuario.id, "lote-dois-casos-b")
    arquivo_evento_a = _criar_arquivo_lote(session, lote_a.id, "evento_a.xml")
    arquivo_evento_b = _criar_arquivo_lote(session, lote_b.id, "evento_b.xml")
    session.close()

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")

    resultado_evento_a = processar_xml_nfe(
        str(xml_evento), CNPJ_CLIENTE, caso_a.id, arquivo_evento_a.id
    )
    assert resultado_evento_a["status"] == "evento"

    resultado_evento_b = processar_xml_nfe(
        str(xml_evento), CNPJ_CLIENTE, caso_b.id, arquivo_evento_b.id
    )
    assert resultado_evento_b["status"] == "evento"  # não "ja_existente" cruzando o caso A

    session = db_session_factory()
    eventos = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).all()
    assert len(eventos) == 2
    assert {e.cliente_caso_id for e in eventos} == {caso_a.id, caso_b.id}
    assert all(e.nota_id is None for e in eventos)  # órfão nos dois, nenhuma nota existe


def test_evento_sem_ret_evento_reenviado_nao_duplica_linha(db_session_factory, tmp_path):
    """cstat vazio (sem retEvento) precisa contar como valor normal na
    UNIQUE, não como NULL -- senão o mesmo pedido reenviado várias vezes
    cria uma linha nova a cada upload."""
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-sem-ret-evento-repetido")
    arquivo_1 = _criar_arquivo_lote(session, lote.id, "evento1.xml")
    arquivo_2 = _criar_arquivo_lote(session, lote.id, "evento2.xml")
    session.close()

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE, com_ret_evento=False), encoding="utf-8")

    resultado_1 = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_1.id)
    assert resultado_1["status"] == "evento"
    resultado_2 = processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_2.id)
    assert resultado_2["status"] == "ja_existente"

    session = db_session_factory()
    eventos = session.query(EventoNFe).filter_by(chave_acesso=CHAVE).all()
    assert len(eventos) == 1


def test_nota_com_cnpj_divergente_continua_erro_de_nota(db_session_factory, tmp_path):
    """classificar_tipo levanta NFeParseError quando o CNPJ do cliente não
    bate com emitente nem destinatário -- não pode ser desviado para o
    parser de evento."""
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-cnpj-divergente")
    arquivo = _criar_arquivo_lote(session, lote.id, "nota.xml")
    session.close()

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")

    resultado = processar_xml_nfe(str(xml_nota), "00000000000000", caso.id, arquivo.id)
    assert resultado["status"] == "erro"
    assert "CNPJ do cliente" in resultado["motivo"]


def test_arquivo_que_nao_e_nem_nota_nem_evento_reporta_erro_de_nota(db_session_factory, tmp_path):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-nem-nem")
    arquivo = _criar_arquivo_lote(session, lote.id, "nao_e_nada.xml")
    session.close()

    xml_path = tmp_path / "nao_e_nada.xml"
    xml_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><algumaCoisa><x>1</x></algumaCoisa>',
        encoding="utf-8",
    )

    resultado = processar_xml_nfe(str(xml_path), CNPJ_CLIENTE, caso.id, arquivo.id)
    assert resultado["status"] == "erro"
    assert "infNFe" in resultado["motivo"]  # erro ORIGINAL do parser de nota, não do de evento


def test_varredura_dispara_so_quando_ultimo_arquivo_do_lote_termina(
    db_session_factory, tmp_path, monkeypatch
):
    """A varredura de pendentes não pode depender de um countdown fixo --
    dispara a partir de _atualizar_status_arquivo_lote, e só quando não
    sobra nenhum ArquivoLote do mesmo lote em PENDENTE/PROCESSANDO."""
    fake_delay = MagicMock()
    monkeypatch.setattr(tasks_module.aplicar_eventos_pendentes, "delay", fake_delay)

    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-varredura")
    arquivo_1 = _criar_arquivo_lote(session, lote.id, "nota1.xml")
    arquivo_2 = _criar_arquivo_lote(session, lote.id, "nota2.xml")
    session.close()

    chave_1 = "1" * 44
    chave_2 = "2" * 44
    xml_nota_1 = tmp_path / "nota1.xml"
    xml_nota_1.write_text(XML_NOTA_TEMPLATE.format(chave=chave_1), encoding="utf-8")
    xml_nota_2 = tmp_path / "nota2.xml"
    xml_nota_2.write_text(XML_NOTA_TEMPLATE.format(chave=chave_2), encoding="utf-8")

    processar_xml_nfe(str(xml_nota_1), CNPJ_CLIENTE, caso.id, arquivo_1.id)
    fake_delay.assert_not_called()  # arquivo_2 ainda está PENDENTE

    processar_xml_nfe(str(xml_nota_2), CNPJ_CLIENTE, caso.id, arquivo_2.id)
    fake_delay.assert_called_once_with(caso.id)


def test_aplicar_eventos_pendentes_varre_e_aplica_orfaos_do_caso(
    db_session_factory, tmp_path, monkeypatch
):
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-sweep-aplica")
    arquivo_evento = _criar_arquivo_lote(session, lote.id, "evento.xml")
    arquivo_nota = _criar_arquivo_lote(session, lote.id, "nota.xml")
    session.close()

    xml_evento = tmp_path / "evento.xml"
    xml_evento.write_text(_xml_evento_cancelamento(CHAVE), encoding="utf-8")
    processar_xml_nfe(str(xml_evento), CNPJ_CLIENTE, caso.id, arquivo_evento.id)

    xml_nota = tmp_path / "nota.xml"
    xml_nota.write_text(XML_NOTA_TEMPLATE.format(chave=CHAVE), encoding="utf-8")
    # Simula o crash que a varredura existe para cobrir: a nota chega e o
    # commit acontece, mas a aplicação do pendente (via
    # _aplicar_eventos_pendentes_da_chave) nunca roda.
    monkeypatch.setattr(
        tasks_module, "_aplicar_eventos_pendentes_da_chave", lambda *a, **k: None
    )
    processar_xml_nfe(str(xml_nota), CNPJ_CLIENTE, caso.id, arquivo_nota.id)

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.AUTORIZADA  # ainda não aplicado
    session.close()

    resultado = aplicar_eventos_pendentes(caso.id)
    assert resultado == {"status": "ok", "verificados": 1, "aplicados": 1, "com_falha": 0}

    session = db_session_factory()
    nota = session.query(Nota).filter_by(chave_acesso=CHAVE).one()
    assert nota.situacao == SituacaoNota.CANCELADA


def test_aplicar_eventos_pendentes_isola_falha_de_um_evento_e_continua(
    db_session_factory, tmp_path, monkeypatch
):
    """Um evento com efeito quebrado não pode abortar a varredura inteira --
    os demais pendentes do caso continuam sendo tentados."""
    session = db_session_factory()
    caso = _criar_caso(session)
    usuario = _criar_usuario(session)
    lote = _criar_lote(session, caso.id, usuario.id, "lote-sweep-falha")
    arquivo_evento_ok = _criar_arquivo_lote(session, lote.id, "evento_ok.xml")
    arquivo_evento_quebrado = _criar_arquivo_lote(session, lote.id, "evento_quebrado.xml")
    session.close()

    chave_ok = "3" * 44
    chave_quebrada = "4" * 44
    xml_evento_ok = tmp_path / "evento_ok.xml"
    xml_evento_ok.write_text(_xml_evento_cancelamento(chave_ok), encoding="utf-8")
    xml_evento_quebrado = tmp_path / "evento_quebrado.xml"
    xml_evento_quebrado.write_text(_xml_evento_cancelamento(chave_quebrada), encoding="utf-8")

    processar_xml_nfe(str(xml_evento_ok), CNPJ_CLIENTE, caso.id, arquivo_evento_ok.id)
    processar_xml_nfe(str(xml_evento_quebrado), CNPJ_CLIENTE, caso.id, arquivo_evento_quebrado.id)

    session = db_session_factory()
    evento_quebrado_id = (
        session.query(EventoNFe.id).filter_by(chave_acesso=chave_quebrada).scalar()
    )
    session.close()

    original = tasks_module._aplicar_efeito_evento

    def _aplicar_efeito_evento_com_falha(db, evento_id):
        if evento_id == evento_quebrado_id:
            raise RuntimeError("falha simulada")
        return original(db, evento_id)

    monkeypatch.setattr(
        tasks_module, "_aplicar_efeito_evento", _aplicar_efeito_evento_com_falha
    )

    resultado = aplicar_eventos_pendentes(caso.id)
    assert resultado == {"status": "ok", "verificados": 2, "aplicados": 0, "com_falha": 1}

    # ambos ficam órfãos (sem nota) e o efeito do evento OK nunca era
    # esperado aplicar de qualquer forma -- o que importa aqui é que a
    # exceção no quebrado não impediu a tentativa no OK.
    session = db_session_factory()
    eventos = {e.chave_acesso: e for e in session.query(EventoNFe).all()}
    assert eventos[chave_ok].aplicado is False  # órfão -- sem nota, não há o que aplicar
    assert eventos[chave_quebrada].aplicado is False
