"""
Geração do DANFE (Documento Auxiliar da NF-e) em PDF a partir do XML original.

Determinístico, sem IA: o layout é o padrão da NF-e e quem desenha é a
biblioteca brazilfiscalreport. O PDF é só uma representação para leitura --
o documento com validade jurídica continua sendo o XML assinado.
"""
from brazilfiscalreport.danfe import Danfe, DanfeConfig
from lxml import etree

NS_NFE = "{http://www.portalfiscal.inf.br/nfe}"


class ErroGeracaoDanfe(Exception):
    """O XML não pôde ser convertido em DANFE (malformado ou incompleto)."""


def gerar_danfe_pdf(xml: bytes, cancelada: bool) -> bytes:
    """
    Devolve o PDF do DANFE. `cancelada` vem de Nota.situacao, e não do XML:
    o cancelamento chega num XML de evento separado, então o XML da nota
    nunca diz que ela foi cancelada.
    """
    try:
        modelo = etree.fromstring(xml).findtext(f".//{NS_NFE}ide/{NS_NFE}mod")
    except etree.XMLSyntaxError as exc:
        raise ErroGeracaoDanfe(f"XML malformado: {exc}") from exc
    # O layout do DANFE é o da NF-e (modelo 55). Uma NFC-e (65) sairia com
    # cara de NF-e, o que é enganoso numa peça -- melhor ficar de fora.
    if modelo is not None and modelo != "55":
        raise ErroGeracaoDanfe(f"modelo {modelo} não é NF-e (55)")

    try:
        danfe = Danfe(xml=xml, config=DanfeConfig(watermark_cancelled=cancelada))
        return bytes(danfe.output())
    except Exception as exc:
        # A biblioteca não tem exceção própria: XML malformado vira ParseError,
        # grupo obrigatório ausente vira KeyError/AttributeError no desenho.
        raise ErroGeracaoDanfe(f"{type(exc).__name__}: {exc}") from exc
