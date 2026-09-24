"""
Parser determinístico de eventos de NF-e (XML) usando lxml.

Propositalmente NÃO usa IA, pelo mesmo motivo do parser de nota (ver
app/parsers/nfe_parser.py): o schema de evento é público e estável.

Um evento é um XML separado do XML da nota, com estrutura própria, gerado
depois da emissão e vinculado à nota pela chave de acesso (cancelamento,
carta de correção, manifestação do destinatário etc.). Referência de tags:

- infEvento/chNFe                      -> chave de acesso da nota (44 dígitos)
- infEvento/tpEvento                   -> tipo do evento (ver TIPO_CANCELAMENTO)
- infEvento/nSeqEvento                 -> número de sequência do evento
- infEvento/dhEvento                   -> data/hora do evento
- infEvento/tpAmb                      -> ambiente (1=produção, 2=homologação)
- infEvento/detEvento/xJust ou xCorrecao -> justificativa/texto do evento
- infEvento/detEvento/descEvento       -> descrição do evento
- retEvento/infEvento/cStat            -> status do PROTOCOLO do Sefaz
- retEvento/infEvento/xMotivo          -> motivo do status
- retEvento/infEvento/nProt            -> número do protocolo

Este parser só extrai dados. Ele NÃO decide se o evento pode alterar a nota
-- essa política (quais tpEvento agem, quais cStat contam como registrado
pelo Sefaz) fica no worker (app/workers/tasks.py), no mesmo espírito de
app/core/sql_seguranca.py: a leitura não decide, a regra decide.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.parsers.nfe_parser import NFE_NS, _XML_PARSER, _find, _findall, _text
from lxml import etree

# Tipo de evento que efetivamente cancela a nota. Os demais (carta de
# correção, manifestações do destinatário, EPEC etc.) são apenas
# armazenados nesta versão -- ver "O que falta" no README.
TIPO_CANCELAMENTO = "110111"


class EventoParseError(Exception):
    """Erro ao processar um XML de evento (arquivo malformado, schema
    inesperado etc.). Propositalmente NÃO herda de NFeParseError: o worker
    tenta parse_nfe_xml primeiro e cai para parse_evento_xml só quando esse
    levanta NFeParseError -- se as duas exceções fossem a mesma classe, um
    evento genuíno mas malformado seria reportado com a mensagem errada."""


@dataclass
class EventoNFeDTO:
    chave_acesso: str
    tipo_evento: str
    numero_sequencia: int
    descricao_evento: Optional[str]
    data_evento: Optional[datetime]
    justificativa: Optional[str]
    tp_amb: Optional[str]
    protocolo: Optional[str]
    cstat: Optional[str]
    motivo: Optional[str]


def _parse_data_evento(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_evento_xml(xml_path: str | Path) -> EventoNFeDTO:
    """
    Lê um único arquivo XML de evento de NF-e e retorna os dados extraídos.
    Levanta EventoParseError se o arquivo não parecer um evento válido.
    """
    xml_path = Path(xml_path)
    try:
        tree = etree.parse(str(xml_path), parser=_XML_PARSER)
    except etree.XMLSyntaxError as exc:
        raise EventoParseError(f"XML malformado em {xml_path.name}: {exc}") from exc

    root = tree.getroot()

    # Um arquivo pode trazer mais de um <evento> (envEvento em lote, usado
    # por alguns emissores para mandar vários cancelamentos juntos). Ler só
    # o primeiro com .find() perderia os demais em silêncio -- o arquivo
    # seria marcado como processado com sucesso e os outros cancelamentos
    # nunca chegariam a existir no sistema. Melhor recusar explicitamente
    # (vira ERRO visível) do que fingir sucesso parcial.
    eventos = root.findall(".//nfe:evento", namespaces=NFE_NS) or root.findall(".//evento")
    if len(eventos) > 1:
        raise EventoParseError(
            f"{xml_path.name} contém {len(eventos)} eventos no mesmo arquivo -- "
            "envEvento em lote não é suportado, separe em um arquivo por evento."
        )

    if eventos:
        # infEvento pode aparecer duas vezes no mesmo arquivo: uma dentro de
        # <evento> (o que foi pedido) e outra dentro de <retEvento> (o que o
        # Sefaz respondeu). Aqui é sempre a do pedido.
        inf_evento = _find(eventos[0], "infEvento")
    elif etree.QName(root.tag).localname == "infEvento":
        # Exportador de terceiros removeu o <evento> e deixou só <infEvento>
        # solto como raiz -- mesma tolerância a variação de estrutura que
        # app/parsers/nfe_parser.py já tem para xmlns ausente.
        inf_evento = root
    else:
        inf_evento = root.find(".//nfe:infEvento", namespaces=NFE_NS)
        if inf_evento is None:
            inf_evento = root.find(".//infEvento")

    if inf_evento is None:
        raise EventoParseError(
            f"Não foi encontrado <infEvento> em {xml_path.name} — não parece ser um evento de NF-e."
        )

    chave_acesso = _text(inf_evento, "chNFe") or ""
    if not chave_acesso:
        raise EventoParseError(f"chNFe ausente em {xml_path.name}.")

    tipo_evento = _text(inf_evento, "tpEvento") or ""
    if not tipo_evento:
        raise EventoParseError(f"tpEvento ausente em {xml_path.name}.")

    numero_sequencia_texto = _text(inf_evento, "nSeqEvento")
    numero_sequencia = int(numero_sequencia_texto) if numero_sequencia_texto else 1

    det_evento = _find(inf_evento, "detEvento")
    justificativa = None
    descricao_evento = None
    if det_evento is not None:
        descricao_evento = _text(det_evento, "descEvento")
        # xJust: cancelamento. xCorrecao: carta de correção. Cada tipo de
        # evento usa um nome de campo diferente para o texto livre.
        justificativa = _text(det_evento, "xJust") or _text(det_evento, "xCorrecao")

    # retEvento/infEvento é o PROTOCOLO do Sefaz -- pode não existir (o
    # arquivo é só o pedido de evento, ainda sem resposta).
    ret_inf_evento = root.find(".//nfe:retEvento/nfe:infEvento", namespaces=NFE_NS)
    if ret_inf_evento is None:
        ret_inf_evento = root.find(".//retEvento/infEvento")

    protocolo = _text(ret_inf_evento, "nProt") if ret_inf_evento is not None else None
    cstat = _text(ret_inf_evento, "cStat") if ret_inf_evento is not None else None
    motivo = _text(ret_inf_evento, "xMotivo") if ret_inf_evento is not None else None

    # dhEvento (data do pedido) é a primeira escolha; se vier ausente ou
    # ilegível, cai para dhRegEvento (data do registro no Sefaz) antes de
    # desistir -- uma nota CANCELADA sem data nenhuma é ruim como prova
    # documental, e as duas datas costumam ser segundos uma da outra.
    data_evento = _parse_data_evento(_text(inf_evento, "dhEvento"))
    if data_evento is None and ret_inf_evento is not None:
        data_evento = _parse_data_evento(_text(ret_inf_evento, "dhRegEvento"))

    return EventoNFeDTO(
        chave_acesso=chave_acesso,
        tipo_evento=tipo_evento,
        numero_sequencia=numero_sequencia,
        descricao_evento=descricao_evento,
        data_evento=data_evento,
        justificativa=justificativa,
        tp_amb=_text(inf_evento, "tpAmb"),
        protocolo=protocolo,
        cstat=cstat,
        motivo=motivo,
    )
