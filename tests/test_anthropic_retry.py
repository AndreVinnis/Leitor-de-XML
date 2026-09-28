"""
Cobre a política de retry/backoff das chamadas ao SDK da Anthropic
(app/ai/anthropic_retry.py) e sua aplicação em consulta_nl_sql. O
normalizador_produtos não usa essa política (o retry dele é o do lote, em
app/workers/tasks.py). embeddings.py continua no Gemini -- ver
tests/test_gemini_retry.py.
"""

from unittest.mock import MagicMock

import anthropic
import httpx2
import pytest
import tenacity

from app.ai.anthropic_retry import _deve_tentar_novamente


def _fake_response(status_code: int, body: dict) -> httpx2.Response:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx2.Response(status_code, request=request, json=body)


def _api_status_error(cls, status_code: int, tipo: str, mensagem: str):
    response = _fake_response(status_code, {"error": {"type": tipo, "message": mensagem}})
    return cls(mensagem, response=response, body=response.json())


def _rate_limit_error():
    return _api_status_error(anthropic.RateLimitError, 429, "rate_limit_error", "limite")


def _internal_server_error():
    return _api_status_error(anthropic.InternalServerError, 500, "api_error", "indisponível")


def _service_unavailable_error():
    return _api_status_error(
        anthropic.ServiceUnavailableError, 503, "api_error", "indisponível"
    )


def _overloaded_error():
    return _api_status_error(
        anthropic.OverloadedError, 529, "overloaded_error", "sobrecarregado"
    )


def _bad_request_error():
    return _api_status_error(
        anthropic.BadRequestError, 400, "invalid_request_error", "requisição inválida"
    )


def _connection_error():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(request=request)


def _timeout_error():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APITimeoutError(request=request)


class TestDeveTentarNovamente:
    def test_rate_limit_error_tenta_novamente(self):
        assert _deve_tentar_novamente(_rate_limit_error()) is True

    def test_internal_server_error_tenta_novamente(self):
        assert _deve_tentar_novamente(_internal_server_error()) is True

    def test_service_unavailable_error_tenta_novamente(self):
        assert _deve_tentar_novamente(_service_unavailable_error()) is True

    def test_overloaded_error_529_tenta_novamente(self):
        assert _deve_tentar_novamente(_overloaded_error()) is True

    def test_api_connection_error_tenta_novamente(self):
        assert _deve_tentar_novamente(_connection_error()) is True

    def test_api_timeout_error_tenta_novamente(self):
        assert _deve_tentar_novamente(_timeout_error()) is True

    def test_bad_request_error_nao_tenta_novamente(self):
        assert _deve_tentar_novamente(_bad_request_error()) is False

    def test_connection_error_generico_tenta_novamente(self):
        assert _deve_tentar_novamente(ConnectionError("falha de rede")) is True

    def test_timeout_error_generico_tenta_novamente(self):
        assert _deve_tentar_novamente(TimeoutError("tempo esgotado")) is True

    def test_erro_generico_nao_tenta_novamente(self):
        assert _deve_tentar_novamente(ValueError("outra coisa")) is False


def _sem_espera(monkeypatch, funcao_decorada):
    """Zera o backoff de uma função decorada com @retry_anthropic para o
    teste não esperar de verdade entre tentativas."""
    monkeypatch.setattr(funcao_decorada.retry, "wait", tenacity.wait_none())


class TestNormalizadorProdutos:
    def test_nao_retenta_por_conta_propria(self):
        # O retry da normalização é o do lote (app/workers/tasks.py,
        # TENTATIVAS_POR_LOTE) -- um retry aqui multiplicaria as tentativas.
        from app.ai import normalizador_produtos

        client = MagicMock()
        client.messages.create.side_effect = _internal_server_error()

        with pytest.raises(anthropic.InternalServerError):
            normalizador_produtos._gerar_conteudo(client, model="m")

        assert client.messages.create.call_count == 1


class TestConsultaNlSql:
    def test_retenta_erro_transitorio_e_devolve_resultado(self, monkeypatch):
        from app.ai import consulta_nl_sql

        _sem_espera(monkeypatch, consulta_nl_sql._gerar_conteudo)
        client = MagicMock()
        client.messages.create.side_effect = [_rate_limit_error(), "ok"]

        resultado = consulta_nl_sql._gerar_conteudo(client, model="m")

        assert resultado == "ok"
        assert client.messages.create.call_count == 2
