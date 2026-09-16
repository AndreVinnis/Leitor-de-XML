"""Validadores determinísticos de documentos, sem dependência de IA."""


def normalizar_cnpj(valor: str | None) -> str:
    return "".join(filter(str.isdigit, valor or ""))


def validar_digitos_verificadores_cnpj(cnpj: str) -> bool:
    """`cnpj` já deve estar normalizado (só dígitos). Implementa o algoritmo
    módulo 11 oficial da Receita Federal. Sequências de dígito repetido
    (ex: "11111111111111") passam a aritmética do módulo 11 mas não são
    CNPJs reais, por isso são rejeitadas explicitamente."""
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def _digito(base: str, pesos: list[int]) -> int:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _digito(cnpj[:12], pesos1)
    d2 = _digito(cnpj[:12] + str(d1), pesos2)
    return cnpj[-2:] == f"{d1}{d2}"


def validar_cnpj_obrigatorio(valor: str | None) -> str:
    """Normaliza e valida um CNPJ obrigatório. Levanta ValueError com
    mensagem amigável se inválido (tamanho ou dígito verificador)."""
    digitos = normalizar_cnpj(valor)
    if len(digitos) != 14:
        raise ValueError("CNPJ do cliente é obrigatório e deve ter 14 dígitos.")
    if not validar_digitos_verificadores_cnpj(digitos):
        raise ValueError("CNPJ do cliente é inválido (dígito verificador não confere).")
    return digitos
