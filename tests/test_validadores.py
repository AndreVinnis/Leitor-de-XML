import pytest

from app.core.validadores import (
    normalizar_cnpj,
    validar_cnpj_obrigatorio,
    validar_digitos_verificadores_cnpj,
)


class TestNormalizarCnpj:
    def test_remove_pontuacao(self):
        assert normalizar_cnpj("11.222.333/0001-81") == "11222333000181"

    def test_none_vira_string_vazia(self):
        assert normalizar_cnpj(None) == ""


class TestValidarDigitosVerificadoresCnpj:
    def test_cnpj_valido(self):
        assert validar_digitos_verificadores_cnpj("11222333000181") is True

    def test_cnpj_valido_outro(self):
        assert validar_digitos_verificadores_cnpj("11444777000161") is True

    def test_digito_verificador_errado(self):
        assert validar_digitos_verificadores_cnpj("98765432000188") is False

    def test_todos_os_digitos_iguais_e_rejeitado(self):
        assert validar_digitos_verificadores_cnpj("11111111111111") is False

    def test_tamanho_errado(self):
        assert validar_digitos_verificadores_cnpj("112223330001") is False


class TestValidarCnpjObrigatorio:
    def test_cnpj_valido_com_mascara_normaliza(self):
        assert validar_cnpj_obrigatorio("11.222.333/0001-81") == "11222333000181"

    def test_cnpj_valido_sem_mascara(self):
        assert validar_cnpj_obrigatorio("11222333000181") == "11222333000181"

    def test_cnpj_com_tamanho_errado_levanta_value_error(self):
        with pytest.raises(ValueError, match="14 dígitos"):
            validar_cnpj_obrigatorio("123")

    def test_cnpj_com_digito_verificador_errado_levanta_value_error(self):
        with pytest.raises(ValueError, match="dígito verificador"):
            validar_cnpj_obrigatorio("98765432000188")

    def test_none_levanta_value_error(self):
        with pytest.raises(ValueError):
            validar_cnpj_obrigatorio(None)
