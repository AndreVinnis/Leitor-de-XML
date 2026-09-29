from pathlib import Path

import pytest

from app.relatorios.danfe import ErroGeracaoDanfe, gerar_danfe_pdf

XML_COMPLETO = Path(__file__).parent / "fixtures" / "nfe_completa_exemplo.xml"


def test_gerar_danfe_devolve_pdf():
    pdf = gerar_danfe_pdf(XML_COMPLETO.read_bytes(), cancelada=False)

    assert pdf.startswith(b"%PDF-")


def test_gerar_danfe_de_nota_cancelada_devolve_pdf():
    assert gerar_danfe_pdf(XML_COMPLETO.read_bytes(), cancelada=True).startswith(b"%PDF-")


def test_gerar_danfe_recusa_nfce():
    xml = XML_COMPLETO.read_bytes().replace(b"<mod>55</mod>", b"<mod>65</mod>")

    with pytest.raises(ErroGeracaoDanfe, match="modelo 65"):
        gerar_danfe_pdf(xml, cancelada=False)


@pytest.mark.parametrize("xml", [b"", b"<quebrado", b"<NFe/>"])
def test_gerar_danfe_de_xml_invalido_levanta_erro_proprio(xml):
    with pytest.raises(ErroGeracaoDanfe):
        gerar_danfe_pdf(xml, cancelada=False)
