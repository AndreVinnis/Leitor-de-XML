import time

import pytest

from app.core.config import settings
from app.core.tokens import (
    TokenExpirado,
    TokenInvalido,
    gerar_token_aprovacao,
    verificar_token_aprovacao,
)


def test_gerar_e_verificar_token_roundtrip():
    token = gerar_token_aprovacao(admin_id=1, usuario_id=2, acao="aprovar")
    payload = verificar_token_aprovacao(token)
    assert payload == {"admin_id": 1, "usuario_id": 2, "acao": "aprovar"}


def test_token_adulterado_e_invalido():
    token = gerar_token_aprovacao(admin_id=1, usuario_id=2, acao="aprovar")
    ultimo_char = "a" if token[-1] != "a" else "b"
    adulterado = token[:-1] + ultimo_char

    with pytest.raises(TokenInvalido):
        verificar_token_aprovacao(adulterado)


def test_token_completamente_invalido():
    with pytest.raises(TokenInvalido):
        verificar_token_aprovacao("isso-nao-e-um-token-valido")


def test_token_expirado(monkeypatch):
    monkeypatch.setattr(settings, "token_aprovacao_expira_minutos", 0)
    token = gerar_token_aprovacao(admin_id=1, usuario_id=2, acao="aprovar")

    time.sleep(1.1)  # garante que o "age" (resolução de 1s) passe do max_age=0

    with pytest.raises(TokenExpirado):
        verificar_token_aprovacao(token)
