"""
Gera um lote de XMLs de NF-e sintéticos para teste de carga do upload
(não são notas reais nem de nenhum ambiente da SEFAZ).

Uso: python3 tests/gerar_lote_teste.py
Gera 100 arquivos em tests/fixtures/lote_teste_100/
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

OUT_DIR = Path(__file__).parent / "fixtures" / "lote_teste_100"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CLIENTE_CNPJ = "98765432000188"
CLIENTE_NOME = "CLIENTE EXEMPLO LTDA"

CONTRAPARTES = [
    ("11222333000181", "DISTRIBUIDORA ALFA LTDA"),
    ("22333444000162", "ATACADO BETA COMERCIO LTDA"),
    ("33444555000143", "MERCADO GAMA SUPERMERCADOS LTDA"),
    ("44555666000124", "COMERCIAL DELTA EIRELI"),
    ("55666777000105", "EPSILON DISTRIBUIDORA S.A."),
    ("66777888000186", "ZETA ATACADISTA LTDA"),
    ("77888999000167", "COMERCIO ETA LTDA"),
    ("88999000000148", "THETA COMERCIO DE ALIMENTOS LTDA"),
]

# (codigo, descricao, NCM, unidade, preco_unit_base)
PRODUTOS = [
    ("001", "ARROZ TIO JOAO 5KG", "10063021", "UN", 25.50),
    ("002", "FEIJAO CARIOCA 1KG", "07133399", "UN", 8.00),
    ("003", "ACUCAR UNIAO 1KG", "17019900", "UN", 5.20),
    ("004", "OLEO SOJA LIZA 900ML", "15071000", "UN", 9.80),
    ("005", "CAFE PILAO 500G", "09011110", "UN", 14.90),
    ("006", "LEITE NINHO INTEGRAL 400G", "04022110", "UN", 22.30),
    ("007", "MACARRAO BARILLA 500G", "19021900", "UN", 6.50),
    ("008", "SARDINHA COQUEIRO LATA 125G", "16041300", "UN", 4.30),
    ("009", "MOLHO TOMATE FUGINI 340G", "20029000", "UN", 3.60),
    ("010", "SAL REFINADO CISNE 1KG", "25010020", "UN", 2.90),
    ("011", "FARINHA DE TRIGO DONA BENTA 1KG", "11010010", "UN", 6.10),
    ("012", "BISCOITO MAIZENA PIRAQUE 200G", "19053100", "UN", 4.80),
]

# Produtos com inconsistência proposital: quantidade vendida (saida) vai
# ficar bem maior que a comprada (entrada) -- simula "venda sem estoque
# correspondente", útil quando o motor de reconciliação for implementado.
PRODUTOS_DESBALANCEADOS = {"005", "009"}

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe>
    <infNFe Id="NFe{chave}" versao="4.00">
      <ide>
        <nNF>{numero}</nNF>
        <serie>1</serie>
        <dhEmi>{dh_emi}</dhEmi>
      </ide>
      <emit>
        <CNPJ>{emit_cnpj}</CNPJ>
        <xNome>{emit_nome}</xNome>
      </emit>
      <dest>
        <CNPJ>{dest_cnpj}</CNPJ>
        <xNome>{dest_nome}</xNome>
      </dest>
{itens_xml}      <total>
        <ICMSTot>
          <vNF>{valor_total:.2f}</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
"""

ITEM_TEMPLATE = """      <det nItem="{n_item}">
        <prod>
          <cProd>{cprod}</cProd>
          <xProd>{xprod}</xProd>
          <NCM>{ncm}</NCM>
          <CFOP>{cfop}</CFOP>
          <uCom>{ucom}</uCom>
          <qCom>{qcom:.4f}</qCom>
          <vUnCom>{vuncom:.4f}</vUnCom>
          <vProd>{vprod:.2f}</vProd>
        </prod>
      </det>
"""


def gerar_chave(seq: int, cnpj_emit: str) -> str:
    # Formato de 44 dígitos (não é uma chave real/validável na SEFAZ,
    # só serve para ser única e ter o tamanho certo para teste local).
    cuf = "35"
    aamm = "2608"
    mod = "55"
    serie = "001"
    nnf = f"{seq:09d}"
    tpemis = "1"
    cnf = f"{seq:08d}"
    cdv = "0"
    return f"{cuf}{aamm}{cnpj_emit}{mod}{serie}{nnf}{tpemis}{cnf}{cdv}"


def gerar_nota(seq: int, dt_base: datetime) -> str:
    tipo = "saida" if random.random() < 0.55 else "entrada"
    contraparte_cnpj, contraparte_nome = random.choice(CONTRAPARTES)

    if tipo == "saida":
        emit_cnpj, emit_nome = CLIENTE_CNPJ, CLIENTE_NOME
        dest_cnpj, dest_nome = contraparte_cnpj, contraparte_nome
        cfop = "5102"
    else:
        emit_cnpj, emit_nome = contraparte_cnpj, contraparte_nome
        dest_cnpj, dest_nome = CLIENTE_CNPJ, CLIENTE_NOME
        cfop = "1102"

    n_itens = random.randint(1, 3)
    produtos_nota = random.sample(PRODUTOS, n_itens)

    itens_xml = ""
    valor_total = 0.0
    for i, (cprod, xprod, ncm, ucom, preco_base) in enumerate(produtos_nota, start=1):
        qtd = random.randint(1, 10)
        if cprod in PRODUTOS_DESBALANCEADOS and tipo == "saida":
            qtd = random.randint(15, 30)  # vende bem mais do que compra
        vuncom = round(preco_base * random.uniform(0.95, 1.08), 4)
        vprod = round(qtd * vuncom, 2)
        valor_total += vprod
        itens_xml += ITEM_TEMPLATE.format(
            n_item=i, cprod=cprod, xprod=xprod, ncm=ncm, cfop=cfop,
            ucom=ucom, qcom=float(qtd), vuncom=vuncom, vprod=vprod,
        )

    chave = gerar_chave(seq, emit_cnpj)
    dh_emi = (dt_base + timedelta(hours=seq)).strftime("%Y-%m-%dT%H:%M:%S-03:00")

    return TEMPLATE.format(
        chave=chave, numero=seq, dh_emi=dh_emi,
        emit_cnpj=emit_cnpj, emit_nome=emit_nome,
        dest_cnpj=dest_cnpj, dest_nome=dest_nome,
        itens_xml=itens_xml, valor_total=valor_total,
    )


def main():
    dt_base = datetime(2026, 8, 1)
    for seq in range(1, 101):
        xml_content = gerar_nota(seq, dt_base)
        destino = OUT_DIR / f"nfe_{seq:03d}.xml"
        destino.write_text(xml_content, encoding="utf-8")
    print(f"Gerados 100 arquivos em: {OUT_DIR}")
    print(f"CNPJ do cliente a usar no campo 'cnpj_cliente' do upload: {CLIENTE_CNPJ}")


if __name__ == "__main__":
    main()
