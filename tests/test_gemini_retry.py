"""
Cobre a política de retry/backoff das chamadas ao SDK do Gemini
(app/ai/gemini_retry.py) e sua aplicação nos três call sites
(normalizador_produtos, embeddings, consulta_nl_sql).

Os testes de integração zeram `wait` via `<funcao>.retry.wait` (atributo
mutável que o decorator @tenacity.retry expõe) para não deixar a suíte lenta
com o backoff exponencial de verdade.
"""

from unittest.mock import MagicMock

import pytest
import tenacity
from google.genai import errors as genai_errors

from app.ai.gemini_retry import _deve_tentar_novamente


def _server_error(code=503):
    return genai_errors.ServerError(code, {"error": {"message": "indisponível"}})


def _client_error(code):
    return genai_errors.ClientError(code, {"error": {"message": "erro de cliente"}})


class TestDeveTentarNovamente:
    def test_server_error_tenta_novamente(self):
        assert _deve_tentar_novamente(_server_error(503)) is True

    def test_client_error_429_tenta_novamente(self):
        assert _deve_tentar_novamente(_client_error(429)) is True

    def test_client_error_400_nao_tenta_novamente(self):
        assert _deve_tentar_novamente(_client_error(400)) is False

    def test_client_error_401_nao_tenta_novamente(self):
        assert _deve_tentar_novamente(_client_error(401)) is False

    def test_connection_error_tenta_novamente(self):
        assert _deve_tentar_novamente(ConnectionError("falha de rede")) is True

    def test_timeout_error_tenta_novamente(self):
        assert _deve_tentar_novamente(TimeoutError("tempo esgotado")) is True

    def test_erro_generico_nao_tenta_novamente(self):
        assert _deve_tentar_novamente(ValueError("outra coisa")) is False


def _sem_espera(monkeypatch, funcao_decorada):
    """Zera o backoff de uma função decorada com @retry_gemini para o teste
    não esperar de verdade entre tentativas."""
    monkeypatch.setattr(funcao_decorada.retry, "wait", tenacity.wait_none())


class TestNormalizadorProdutos:
    def test_retenta_erro_transitorio_e_devolve_resultado(self, monkeypatch):
        from app.ai import normalizador_produtos

        _sem_espera(monkeypatch, normalizador_produtos._gerar_conteudo)
        client = MagicMock()
        client.models.generate_content.side_effect = [_server_error(503), "ok"]

        resultado = normalizador_produtos._gerar_conteudo(client, model="m", contents="c")

        assert resultado == "ok"
        assert client.models.generate_content.call_count == 2

    def test_esgota_tentativas_e_relanca(self, monkeypatch):
        from app.ai import normalizador_produtos

        _sem_espera(monkeypatch, normalizador_produtos._gerar_conteudo)
        client = MagicMock()
        client.models.generate_content.side_effect = _server_error(503)

        with pytest.raises(genai_errors.ServerError):
            normalizador_produtos._gerar_conteudo(client, model="m", contents="c")

        assert client.models.generate_content.call_count == 3

    def test_erro_de_cliente_permanente_nao_retenta(self, monkeypatch):
        from app.ai import normalizador_produtos

        _sem_espera(monkeypatch, normalizador_produtos._gerar_conteudo)
        client = MagicMock()
        client.models.generate_content.side_effect = _client_error(400)

        with pytest.raises(genai_errors.ClientError):
            normalizador_produtos._gerar_conteudo(client, model="m", contents="c")

        assert client.models.generate_content.call_count == 1


class TestConsultaNlSql:
    def test_retenta_erro_transitorio_e_devolve_resultado(self, monkeypatch):
        from app.ai import consulta_nl_sql

        _sem_espera(monkeypatch, consulta_nl_sql._gerar_conteudo)
        client = MagicMock()
        client.models.generate_content.side_effect = [_client_error(429), "ok"]

        resultado = consulta_nl_sql._gerar_conteudo(client, model="m", contents="c")

        assert resultado == "ok"
        assert client.models.generate_content.call_count == 2


class TestEmbeddings:
    def test_retenta_apenas_o_lote_que_falhou(self, monkeypatch):
        from app.ai import embeddings

        _sem_espera(monkeypatch, embeddings._embed_lote)
        client = MagicMock()
        client.models.embed_content.side_effect = [_server_error(500), "ok"]

        resultado = embeddings._embed_lote(client, model="m", contents=["x"])

        assert resultado == "ok"
        assert client.models.embed_content.call_count == 2
