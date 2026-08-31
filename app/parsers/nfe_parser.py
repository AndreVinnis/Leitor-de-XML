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


def _text(node, xpath: str) -> Optional[str]:
    result = node.find(xpath, namespaces=NFE_NS)
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
        tree = etree.parse(str(xml_path))
    except etree.XMLSyntaxError as exc:
        raise NFeParseError(f"XML malformado em {xml_path.name}: {exc}") from exc

    root = tree.getroot()
    inf_nfe = root.find(".//nfe:infNFe", namespaces=NFE_NS)
    if inf_nfe is None:
        raise NFeParseError(f"Não foi encontrado <infNFe> em {xml_path.name} — não parece ser uma NF-e.")

    chave = inf_nfe.get("Id", "")
    chave_acesso = chave.replace("NFe", "") if chave else ""
    if not chave_acesso:
        raise NFeParseError(f"Chave de acesso ausente em {xml_path.name}.")

    ide = inf_nfe.find("nfe:ide", namespaces=NFE_NS)
    emit = inf_nfe.find("nfe:emit", namespaces=NFE_NS)
    dest = inf_nfe.find("nfe:dest", namespaces=NFE_NS)
    total = inf_nfe.find("nfe:total/nfe:ICMSTot", namespaces=NFE_NS)

    itens: list[ItemNFeDTO] = []
    for det in inf_nfe.findall("nfe:det", namespaces=NFE_NS):
        prod = det.find("nfe:prod", namespaces=NFE_NS)
        if prod is None:
            continue
        itens.append(
            ItemNFeDTO(
                numero_item=int(det.get("nItem")) if det.get("nItem") else None,
                codigo_produto=_text(prod, "nfe:cProd"),
                descricao_original=_text(prod, "nfe:xProd") or "",
                ncm=_text(prod, "nfe:NCM"),
                cfop=_text(prod, "nfe:CFOP"),
                unidade=_text(prod, "nfe:uCom"),
                quantidade=_decimal(_text(prod, "nfe:qCom")),
                valor_unitario=_decimal(_text(prod, "nfe:vUnCom")),
                valor_total=_decimal(_text(prod, "nfe:vProd")),
            )
        )

    return NotaNFeDTO(
        chave_acesso=chave_acesso,
        numero=_text(ide, "nfe:nNF") if ide is not None else None,
        serie=_text(ide, "nfe:serie") if ide is not None else None,
        data_emissao=_parse_data_emissao(_text(ide, "nfe:dhEmi") if ide is not None else None),
        emitente_cnpj=_text(emit, "nfe:CNPJ") if emit is not None else None,
        emitente_nome=_text(emit, "nfe:xNome") if emit is not None else None,
        destinatario_cnpj=_text(dest, "nfe:CNPJ") if dest is not None else None,
        destinatario_nome=_text(dest, "nfe:xNome") if dest is not None else None,
        valor_total=_decimal(_text(total, "nfe:vNF") if total is not None else None),
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
