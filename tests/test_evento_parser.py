from pathlib import Path

from app.parsers.evento_parser import EventoParseError, parse_evento_xml

FIXTURE_CANCELAMENTO = Path(__file__).parent / "fixtures" / "evento_cancelamento_exemplo.xml"

CHAVE_EXEMPLO = "35240512345678000199550010000001231234567890"


def test_parse_evento_cancelamento_basico():
    evento = parse_evento_xml(FIXTURE_CANCELAMENTO)

    assert evento.chave_acesso == CHAVE_EXEMPLO
    assert evento.tipo_evento == "110111"
    assert evento.numero_sequencia == 1
    assert evento.descricao_evento == "Cancelamento"
    assert evento.justificativa == "Erro na emissao do documento fiscal"
    assert evento.tp_amb == "1"
    assert evento.protocolo == "135240000000001"
    assert evento.cstat == "135"
    assert evento.motivo == "Evento registrado e vinculado a NF-e"
    assert evento.data_evento is not None
    assert evento.data_evento.year == 2024


def test_parse_evento_carta_correcao(tmp_path):
    """xCorrecao (não xJust) é o campo de texto livre da CC-e."""
    xml_cce = f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011035{CHAVE_EXEMPLO[2:]}101">
      <cOrgao>35</cOrgao>
      <tpAmb>1</tpAmb>
      <CNPJ>12345678000199</CNPJ>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <dhEvento>2024-05-12T09:00:00-03:00</dhEvento>
      <tpEvento>110110</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <verEvento>1.00</verEvento>
      <detEvento versao="1.00">
        <descEvento>Carta de Correcao</descEvento>
        <xCorrecao>Correcao do endereco de entrega</xCorrecao>
      </detEvento>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>1</tpAmb>
      <cOrgao>35</cOrgao>
      <cStat>135</cStat>
      <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110110</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <nProt>135240000000002</nProt>
    </infEvento>
  </retEvento>
</procEventoNFe>
"""
    xml_path = tmp_path / "cce.xml"
    xml_path.write_text(xml_cce, encoding="utf-8")

    evento = parse_evento_xml(xml_path)
    assert evento.tipo_evento == "110110"
    assert evento.justificativa == "Correcao do endereco de entrega"


def test_parse_evento_sem_xmlns_default(tmp_path):
    """Mesmo defeito de exportador de terceiros já corrigido no parser de
    nota (ver app/parsers/nfe_parser.py): xmlns default ausente no elemento
    raiz não pode impedir a leitura do evento."""
    xml_sem_namespace = f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00">
  <evento versao="1.00">
    <infEvento Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <dhEvento>2024-05-15T10:00:00-03:00</dhEvento>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00">
        <descEvento>Cancelamento</descEvento>
        <xJust>Erro na emissao</xJust>
      </detEvento>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>1</tpAmb>
      <cStat>135</cStat>
      <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <nProt>135240000000003</nProt>
    </infEvento>
  </retEvento>
</procEventoNFe>
"""
    xml_path = tmp_path / "sem_namespace.xml"
    xml_path.write_text(xml_sem_namespace, encoding="utf-8")

    evento = parse_evento_xml(xml_path)
    assert evento.chave_acesso == CHAVE_EXEMPLO
    assert evento.tipo_evento == "110111"
    assert evento.cstat == "135"


def test_parse_evento_sem_ret_evento_fica_sem_protocolo(tmp_path):
    """Arquivo que só tem <evento> (o pedido), sem <retEvento> (o protocolo
    do Sefaz), é um PEDIDO de cancelamento, não uma confirmação -- cstat
    precisa ficar None para o worker não aplicar o efeito."""
    xml_sem_ret = f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <dhEvento>2024-05-15T10:00:00-03:00</dhEvento>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00">
        <descEvento>Cancelamento</descEvento>
        <xJust>Erro na emissao</xJust>
      </detEvento>
    </infEvento>
  </evento>
</procEventoNFe>
"""
    xml_path = tmp_path / "sem_ret_evento.xml"
    xml_path.write_text(xml_sem_ret, encoding="utf-8")

    evento = parse_evento_xml(xml_path)
    assert evento.cstat is None
    assert evento.protocolo is None
    assert evento.motivo is None


def test_parse_evento_cstat_rejeitado_e_gravado_com_status(tmp_path):
    """cStat de rejeição (não está em {135,136,155}) ainda é extraído --
    quem decide não aplicar o efeito é o worker, não o parser."""
    xml_rejeitado = f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <dhEvento>2024-05-15T10:00:00-03:00</dhEvento>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00">
        <descEvento>Cancelamento</descEvento>
        <xJust>Erro na emissao</xJust>
      </detEvento>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>1</tpAmb>
      <cStat>573</cStat>
      <xMotivo>Rejeicao: evento de cancelamento fora do prazo</xMotivo>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
    </infEvento>
  </retEvento>
</procEventoNFe>
"""
    xml_path = tmp_path / "rejeitado.xml"
    xml_path.write_text(xml_rejeitado, encoding="utf-8")

    evento = parse_evento_xml(xml_path)
    assert evento.cstat == "573"
    assert evento.protocolo is None
    assert "Rejeicao" in evento.motivo


def test_parse_evento_chave_vem_de_chnfe_nao_do_atributo_id(tmp_path):
    """O atributo Id de infEvento é a concatenação "ID"+tpEvento+chNFe+nSeq,
    não a chave de acesso pura -- ler dali sem parsear daria uma chave errada."""
    xml_path = tmp_path / "chave.xml"
    xml_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00"><xJust>Erro</xJust></detEvento>
    </infEvento>
  </evento>
</procEventoNFe>
""",
        encoding="utf-8",
    )

    evento = parse_evento_xml(xml_path)
    assert evento.chave_acesso == CHAVE_EXEMPLO
    assert len(evento.chave_acesso) == 44


def test_parse_evento_arquivo_que_nao_e_evento_levanta_erro(tmp_path):
    xml_path = tmp_path / "nao_e_evento.xml"
    xml_path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><algumaCoisa><x>1</x></algumaCoisa>',
        encoding="utf-8",
    )

    try:
        parse_evento_xml(xml_path)
        assert False, "deveria ter levantado EventoParseError"
    except EventoParseError:
        pass


def test_parse_evento_com_multiplos_eventos_no_mesmo_arquivo_levanta_erro(tmp_path):
    """envEvento em lote (mais de um <evento> no mesmo XML) não é suportado
    -- ler só o primeiro perderia os demais em silêncio, com o arquivo
    marcado como sucesso."""
    chave2 = "8" * 44
    xml_lote = f"""<?xml version="1.0" encoding="UTF-8"?>
<envEvento versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00"><xJust>Erro na emissao</xJust></detEvento>
    </infEvento>
  </evento>
  <evento versao="1.00">
    <infEvento Id="ID11011135{chave2[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{chave2}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00"><xJust>Erro na emissao</xJust></detEvento>
    </infEvento>
  </evento>
</envEvento>
"""
    xml_path = tmp_path / "lote_eventos.xml"
    xml_path.write_text(xml_lote, encoding="utf-8")

    try:
        parse_evento_xml(xml_path)
        assert False, "deveria ter levantado EventoParseError"
    except EventoParseError as exc:
        assert "2 eventos" in str(exc)


def test_parse_evento_raiz_sem_envelope_procevento(tmp_path):
    """Alguns exportadores removem o <evento> e deixam só <infEvento> solto
    como raiz -- mesma tolerância a variação de estrutura que o parser de
    nota já tem para xmlns ausente."""
    xml_solto = f"""<?xml version="1.0" encoding="UTF-8"?>
<infEvento xmlns="http://www.portalfiscal.inf.br/nfe" Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
  <tpAmb>1</tpAmb>
  <chNFe>{CHAVE_EXEMPLO}</chNFe>
  <tpEvento>110111</tpEvento>
  <nSeqEvento>1</nSeqEvento>
  <detEvento versao="1.00"><xJust>Erro na emissao</xJust></detEvento>
</infEvento>
"""
    xml_path = tmp_path / "inf_evento_solto.xml"
    xml_path.write_text(xml_solto, encoding="utf-8")

    evento = parse_evento_xml(xml_path)
    assert evento.chave_acesso == CHAVE_EXEMPLO
    assert evento.tipo_evento == "110111"


def test_parse_evento_sem_dhevento_cai_para_dhregevento(tmp_path):
    xml_path = tmp_path / "sem_dhevento.xml"
    xml_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <evento versao="1.00">
    <infEvento Id="ID11011135{CHAVE_EXEMPLO[2:]}101">
      <tpAmb>1</tpAmb>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <detEvento versao="1.00"><xJust>Erro na emissao</xJust></detEvento>
    </infEvento>
  </evento>
  <retEvento versao="1.00">
    <infEvento>
      <tpAmb>1</tpAmb>
      <cStat>135</cStat>
      <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
      <chNFe>{CHAVE_EXEMPLO}</chNFe>
      <tpEvento>110111</tpEvento>
      <nSeqEvento>1</nSeqEvento>
      <nProt>135240000000009</nProt>
      <dhRegEvento>2024-05-15T10:00:05-03:00</dhRegEvento>
    </infEvento>
  </retEvento>
</procEventoNFe>
""",
        encoding="utf-8",
    )

    evento = parse_evento_xml(xml_path)
    assert evento.data_evento is not None
    assert evento.data_evento.year == 2024


def test_parse_evento_xml_malformado_levanta_erro(tmp_path):
    xml_path = tmp_path / "malformado.xml"
    xml_path.write_text("<procEventoNFe><evento>", encoding="utf-8")

    try:
        parse_evento_xml(xml_path)
        assert False, "deveria ter levantado EventoParseError"
    except EventoParseError:
        pass
