"""
Parser determinístico de NF-e (XML) usando lxml.

Propositalmente NÃO usa IA: o schema da NF-e é público e estável, então
extração aqui deve ser 100% determinística. Ver Instruções do Projeto.

Referência de tags padrão da NF-e:
- infNFe/@Id ou chave de 44 dígitos          -> chave de acesso
- ide/nNF, ide/serie, ide/dhEmi              -> número, série, data
- emit/CNPJ, emit/xNome                      -> emitente
- dest/CNPJ, dest/xNome                      -> destinatário
- det (um por item)                          -> item da nota
  - prod/cProd, prod/xProd, prod/NCM, prod/CFOP
  - prod/uCom, prod/qCom, prod/vUnCom, prod/vProd
- total/ICMSTot/vNF                          -> valor total da nota
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from lxml import etree

# Namespace padrão da NF-e (varia pouco entre versões/estados)
NFE_NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

# Defesa em profundidade contra XXE: desliga resolução de entidade externa,
# acesso de rede e DTD, mesmo que o default do lxml já bloqueie a maior parte
# disso -- não depender só do default da biblioteca.
_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,
)


class NFeParseError(Exception):
    """Erro ao processar um XML de NF-e (arquivo malformado, schema inesperado etc.)."""


@dataclass
class ItemNFeDTO:
    numero_item: Optional[int]
    codigo_produto: Optional[str]
    descricao_original: str
    ncm: Optional[str]
    cfop: Optional[str]
    unidade: Optional[str]
    quantidade: Optional[Decimal]
    valor_unitario: Optional[Decimal]
    valor_total: Optional[Decimal]


@dataclass
class NotaNFeDTO:
    chave_acesso: str
    numero: Optional[str]
    serie: Optional[str]
    data_emissao: Optional[datetime]
    emitente_cnpj: Optional[str]
    emitente_nome: Optional[str]
    destinatario_cnpj: Optional[str]
    destinatario_nome: Optional[str]
    valor_total: Optional[Decimal]
    itens: list[ItemNFeDTO] = field(default_factory=list)
    tipo: Optional[str] = None  # definido depois: 'entrada' ou 'saida', conforme CNPJ do cliente


def _find(node, tag: str):
    """Busca um filho direto por tag, tentando o namespace padrão da NF-e e,
    se não achar, sem namespace algum -- alguns exportadores de terceiros
    remontam o XML e descartam o xmlns default, mesmo a tag existindo."""
    if node is None:
        return None
    result = node.find(f"nfe:{tag}", namespaces=NFE_NS)
    if result is None:
        result = node.find(tag)
    return result


def _findall(node, tag: str):
    if node is None:
        return []
    results = node.findall(f"nfe:{tag}", namespaces=NFE_NS)
    if not results:
        results = node.findall(tag)
    return results


def _text(node, tag: str) -> Optional[str]:
    result = _find(node, tag)
    if result is not None and result.text:
        return result.text.strip()
    return None


def _decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _parse_data_emissao(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # dhEmi normalmente vem como 2024-05-10T14:32:10-03:00
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_nfe_xml(xml_path: str | Path) -> NotaNFeDTO:
    """
    Lê um único arquivo XML de NF-e e retorna os dados extraídos.
    Levanta NFeParseError se o arquivo não parecer uma NF-e válida.
    """
    xml_path = Path(xml_path)
    try:
        tree = etree.parse(str(xml_path), parser=_XML_PARSER)
    except etree.XMLSyntaxError as exc:
        raise NFeParseError(f"XML malformado em {xml_path.name}: {exc}") from exc

    root = tree.getroot()
    inf_nfe = root.find(".//nfe:infNFe", namespaces=NFE_NS)
    if inf_nfe is None:
        inf_nfe = root.find(".//infNFe")
    if inf_nfe is None:
        raise NFeParseError(f"Não foi encontrado <infNFe> em {xml_path.name} — não parece ser uma NF-e.")

    chave = inf_nfe.get("Id", "")
    chave_acesso = chave.replace("NFe", "") if chave else ""
    if not chave_acesso:
        raise NFeParseError(f"Chave de acesso ausente em {xml_path.name}.")

    ide = _find(inf_nfe, "ide")
    emit = _find(inf_nfe, "emit")
    dest = _find(inf_nfe, "dest")
    total = _find(_find(inf_nfe, "total"), "ICMSTot")

    itens: list[ItemNFeDTO] = []
    for det in _findall(inf_nfe, "det"):
        prod = _find(det, "prod")
        if prod is None:
            continue
        itens.append(
            ItemNFeDTO(
                numero_item=int(det.get("nItem")) if det.get("nItem") else None,
                codigo_produto=_text(prod, "cProd"),
                descricao_original=_text(prod, "xProd") or "",
                ncm=_text(prod, "NCM"),
                cfop=_text(prod, "CFOP"),
                unidade=_text(prod, "uCom"),
                quantidade=_decimal(_text(prod, "qCom")),
                valor_unitario=_decimal(_text(prod, "vUnCom")),
                valor_total=_decimal(_text(prod, "vProd")),
            )
        )

    return NotaNFeDTO(
        chave_acesso=chave_acesso,
        numero=_text(ide, "nNF"),
        serie=_text(ide, "serie"),
        data_emissao=_parse_data_emissao(_text(ide, "dhEmi")),
        emitente_cnpj=_text(emit, "CNPJ"),
        emitente_nome=_text(emit, "xNome"),
        destinatario_cnpj=_text(dest, "CNPJ"),
        destinatario_nome=_text(dest, "xNome"),
        valor_total=_decimal(_text(total, "vNF")),
        itens=itens,
    )


def classificar_tipo(nota: NotaNFeDTO, cnpj_cliente: str) -> str:
    """
    Define se a nota é 'entrada' (o cliente comprou) ou 'saida' (o cliente
    vendeu), comparando o CNPJ do cliente do escritório com emitente/destinatário.
    """
    cnpj_cliente = "".join(filter(str.isdigit, cnpj_cliente))
    if nota.destinatario_cnpj == cnpj_cliente:
        return "entrada"
    if nota.emitente_cnpj == cnpj_cliente:
        return "saida"
    raise NFeParseError(
        f"CNPJ do cliente ({cnpj_cliente}) não corresponde a emitente nem "
        f"destinatário na nota {nota.chave_acesso}."
    )
