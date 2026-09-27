"""
Preenchimento determinístico do modelo de frase-resposta da consulta NL→SQL
(app/ai/consulta_nl_sql.py) com os valores reais devolvidos pelo banco.

A IA não escreve o número final diretamente na frase -- ela escreve o SQL que
o produz (consulta de finalidade "resposta") e um modelo com marcadores; quem
extrai o valor do resultado já validado e executado, e decide como exibi-lo,
é este módulo. Fail-closed: qualquer marcador que não bata exatamente com o
que foi executado -- consulta errada, coluna ambígua/inexistente, mais de uma
linha, valor nulo -- derruba a resposta (RespostaInvalida) em vez de arriscar
mostrar um número errado ao advogado, no mesmo espírito de
app/core/sql_seguranca.py.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

_REGEX_MARCADOR = re.compile(r"\{(\d+)\.([a-zA-Z_][a-zA-Z0-9_]*)(?:\|([a-zA-Z_]+))?\}")
_REGEX_DIGITO_FORA_DE_MARCADOR = re.compile(r"\d")

FORMATOS_CONHECIDOS = {"numero", "moeda", "data"}


class RespostaInvalida(ValueError):
    """Levantada quando o modelo de resposta não pode ser preenchido com segurança."""


@dataclass
class ResultadoSql:
    """Uma das consultas já executadas, na ordem em que aparecem no plano (1-based).

    `finalidade` é o que veio do plano da IA ("resposta"/"fontes"/"listagem") --
    um marcador só pode ler de uma consulta "resposta": "fontes"/"listagem"
    listam várias notas/itens, então ler a primeira linha delas daria um
    número arbitrário, não o resultado da pergunta.
    """

    finalidade: str
    colunas: list[str]
    linhas: list[list[Any]]


def _valor_numerico(valor: Any) -> Decimal:
    if valor is None:
        raise RespostaInvalida(
            "O banco devolveu NULL para este marcador. Ajuste o SQL para nunca "
            "devolver NULL aqui (ex.: COALESCE(SUM(...), 0) quando zero for o "
            "valor esperado sem dados correspondentes) -- NULL não pode virar "
            "'0' silenciosamente, seria um dado inventado."
        )
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    raise RespostaInvalida(f"Valor '{valor}' não é numérico.")


def _formatar_numero(valor: Any) -> str:
    numero = _valor_numerico(valor)
    sinal = "-" if numero < 0 else ""
    numero = abs(numero).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if numero == 0:
        sinal = ""

    texto = f"{numero:,.4f}"
    parte_inteira, _, parte_decimal = texto.partition(".")
    parte_decimal = parte_decimal.rstrip("0")
    parte_inteira = parte_inteira.replace(",", ".")

    if not parte_decimal:
        return f"{sinal}{parte_inteira}"
    return f"{sinal}{parte_inteira},{parte_decimal}"


def _formatar_moeda(valor: Any) -> str:
    numero = _valor_numerico(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negativo = numero < 0
    numero = abs(numero)
    if numero == 0:
        negativo = False
    inteiro_str = f"{numero:,.2f}"
    parte_inteira, _, parte_decimal = inteiro_str.partition(".")
    parte_inteira_ptbr = parte_inteira.replace(",", ".")
    sinal = "-" if negativo else ""
    return f"{sinal}R$ {parte_inteira_ptbr},{parte_decimal}"


def _formatar_data(valor: Any) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, str):
        for formato in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(valor[: len(formato) + 2], formato).strftime("%d/%m/%Y")
            except ValueError:
                continue
        raise RespostaInvalida(f"Data '{valor}' em formato não reconhecido.")
    raise RespostaInvalida(f"Valor '{valor}' não é uma data.")


def _formatar_valor(valor: Any, formato: Optional[str]) -> str:
    if formato is None:
        if valor is None:
            return "—"
        if isinstance(valor, Decimal):
            return _formatar_numero(valor)
        return str(valor)
    if formato == "numero":
        return _formatar_numero(valor)
    if formato == "moeda":
        return _formatar_moeda(valor)
    if formato == "data":
        return _formatar_data(valor)
    raise RespostaInvalida(f"Formato de marcador desconhecido: '{formato}'.")


def _remover_mencoes_de_catalogo(texto: str, canonicos_existentes: list[dict]) -> str:
    """Remove do texto qualquer menção literal a nome_canonico/categoria (ex.:
    "Arroz 5kg") antes de checar dígitos soltos -- assim um dígito de
    embalagem só é liberado quando o produto é citado por extenso, nunca por
    estar em algum lugar do catálogo do caso (evita que o dígito de um
    produto qualquer libere um número sem relação nenhuma com ele em outro
    ponto da frase)."""
    for canonico in canonicos_existentes:
        for campo in ("nome_canonico", "categoria"):
            valor = canonico.get(campo)
            if valor:
                texto = re.sub(re.escape(valor), "", texto, flags=re.IGNORECASE)
    return texto


def _validar_sem_numero_inventado(
    modelo: str, pergunta: str, canonicos_existentes: list[dict]
) -> None:
    """
    Garante que nenhum dígito literal fora de um marcador tenha sido
    escrito pela IA sem vir da pergunta do usuário ou de uma menção literal a
    um produto do catálogo (trava contra número de resultado inventado na
    frase -- rede de segurança adicional; a defesa principal é exigir que
    todo valor variável venha de marcador, ver `montar_resposta`).
    """
    texto = _REGEX_MARCADOR.sub("", modelo)
    texto = _remover_mencoes_de_catalogo(texto, canonicos_existentes)

    if not _REGEX_DIGITO_FORA_DE_MARCADOR.search(texto):
        return

    permitidos = set(re.findall(r"\d+", pergunta))
    numeros_no_texto = set(re.findall(r"\d+", texto))
    numeros_nao_permitidos = numeros_no_texto - permitidos
    if numeros_nao_permitidos:
        raise RespostaInvalida(
            "O modelo de resposta contém número fora de marcador que não "
            f"aparece na pergunta nem em menção literal a um produto do catálogo: "
            f"{', '.join(sorted(numeros_nao_permitidos))}."
        )


def montar_resposta(
    modelo: str,
    resultados: list[ResultadoSql],
    pergunta: str,
    canonicos_existentes: list[dict],
) -> str:
    """
    Substitui cada marcador `{N.coluna}` ou `{N.coluna|formato}` de `modelo`
    pelo valor real da consulta N (1-based, finalidade "resposta") em
    `resultados`, formatado em PT-BR. Levanta RespostaInvalida (fail-closed)
    quando: a consulta referenciada não existe ou não é de finalidade
    "resposta"; a coluna não existe ou é ambígua (duplicada); a consulta não
    devolveu exatamente uma linha (uma consulta "resposta" é sempre um
    agregado escalar -- SUM/COUNT/etc. sem GROUP BY -- então mais de uma
    linha indica um SQL malformado, e zero linhas nunca deveria acontecer
    para um agregado sem GROUP BY); o valor é NULL; o formato é desconhecido;
    ou sobra um número literal fora de marcador não rastreável até a
    pergunta/catálogo.
    """
    if not modelo or not modelo.strip():
        raise RespostaInvalida("Modelo de resposta vazio.")

    _validar_sem_numero_inventado(modelo, pergunta, canonicos_existentes)

    def _substituir(match: re.Match) -> str:
        indice_consulta = int(match.group(1))
        nome_coluna = match.group(2)
        formato = match.group(3)

        if formato is not None and formato not in FORMATOS_CONHECIDOS:
            raise RespostaInvalida(f"Formato de marcador desconhecido: '{formato}'.")

        posicao = indice_consulta - 1
        if posicao < 0 or posicao >= len(resultados):
            raise RespostaInvalida(
                f"Marcador referencia a consulta {indice_consulta}, mas só há "
                f"{len(resultados)} consulta(s) executada(s)."
            )
        resultado = resultados[posicao]

        if resultado.finalidade != "resposta":
            raise RespostaInvalida(
                f"Marcador referencia a consulta {indice_consulta}, mas ela tem "
                f"finalidade '{resultado.finalidade}' -- só é permitido referenciar "
                "uma consulta de finalidade 'resposta' (uma consulta 'fontes'/"
                "'listagem' lista várias linhas; ler a primeira seria arbitrário)."
            )

        colunas_lower = [c.lower() for c in resultado.colunas]
        ocorrencias = colunas_lower.count(nome_coluna.lower())
        if ocorrencias == 0:
            raise RespostaInvalida(
                f"Coluna '{nome_coluna}' não existe no resultado da consulta {indice_consulta} "
                f"(colunas disponíveis: {', '.join(resultado.colunas)})."
            )
        if ocorrencias > 1:
            raise RespostaInvalida(
                f"Coluna '{nome_coluna}' aparece mais de uma vez no resultado da "
                f"consulta {indice_consulta} -- use um alias único no SQL."
            )
        indice_coluna = colunas_lower.index(nome_coluna.lower())

        if len(resultado.linhas) != 1:
            raise RespostaInvalida(
                f"A consulta {indice_consulta} (finalidade 'resposta') devolveu "
                f"{len(resultado.linhas)} linha(s), mas precisa devolver exatamente "
                "uma para ser usada na resposta -- revise o SQL (ex.: remova "
                "GROUP BY, ou adicione um filtro que reduza a um único grupo)."
            )

        valor = resultado.linhas[0][indice_coluna]
        return _formatar_valor(valor, formato)

    resultado_final = _REGEX_MARCADOR.sub(_substituir, modelo)
    if "{" in resultado_final or "}" in resultado_final:
        raise RespostaInvalida(
            "O modelo de resposta tem chave '{' ou '}' sobrando fora de um "
            "marcador válido (formato esperado: {N.coluna} ou {N.coluna|formato})."
        )
    return resultado_final
