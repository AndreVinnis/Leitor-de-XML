"""
Limite de tentativas (app/core/limite_taxa.py) e regra mínima de senha
(app/core/auth.py::UserManager.validate_password).

O Redis é trocado por um contador em dict pela fixture autouse `limite_taxa`
de tests/conftest.py; aqui os tetos são baixados via monkeypatch em settings
para não precisar de dezenas de requisições por teste.
"""
from unittest.mock import MagicMock, patch

import pytest
import redis
from fastapi import HTTPException

from app.ai.consulta_nl_sql import ConsultaPlanejada, PlanoConsulta
from app.core import limite_taxa
from app.core.config import settings
from app.models.models import RoleUsuario, StatusCadastro, Usuario
from tests.test_routes_auth_cookie import (  # noqa: F401 -- fixtures reaproveitadas
    HEADER_ANTI_CSRF,
    async_db_session_factory,
    cliente_sem_cookies_residuais,
    usuario_ativo_factory,
)


def test_verificar_passa_ate_o_maximo_e_devolve_429_com_retry_after_depois():
    for _ in range(3):
        limite_taxa.verificar("limite:teste:x", maximo=3, janela_s=60)

    with pytest.raises(HTTPException) as erro:
        limite_taxa.verificar("limite:teste:x", maximo=3, janela_s=60)

    assert erro.value.status_code == 429
    assert erro.value.headers["Retry-After"] == "60"


def test_verificar_e_fail_open_quando_o_redis_cai(monkeypatch):
    def redis_fora(chave, janela_s):
        raise redis.ConnectionError("sem redis")

    monkeypatch.setattr("app.core.limite_taxa._incrementar", redis_fora)

    for _ in range(100):
        limite_taxa.verificar("limite:teste:y", maximo=1, janela_s=60)


@pytest.mark.anyio
async def test_login_bloqueia_por_email_depois_do_limite(
    usuario_ativo_factory, cliente_sem_cookies_residuais, monkeypatch
):
    monkeypatch.setattr(settings, "limite_login_por_email", 3)
    await usuario_ativo_factory(email="alvo@teste.local", senha="SenhaForte123")
    cliente = cliente_sem_cookies_residuais

    def tentar(email, senha="errada-errada"):
        return cliente.post(
            "/api/auth/cookie/login",
            data={"username": email, "password": senha},
            headers=HEADER_ANTI_CSRF,
        )

    assert [tentar("alvo@teste.local").status_code for _ in range(3)] == [400, 400, 400]

    bloqueada = tentar("alvo@teste.local", senha="SenhaForte123")
    assert bloqueada.status_code == 429
    assert "Retry-After" in bloqueada.headers

    # Outro e-mail, mesmo IP: o limite por IP (50) ainda não chegou.
    assert tentar("outra@teste.local").status_code == 400


@pytest.mark.anyio
async def test_login_por_jwt_tambem_e_limitado(
    usuario_ativo_factory, cliente_sem_cookies_residuais, monkeypatch
):
    monkeypatch.setattr(settings, "limite_login_por_email", 1)
    await usuario_ativo_factory(email="jwt@teste.local", senha="SenhaForte123")
    cliente = cliente_sem_cookies_residuais
    dados = {"username": "jwt@teste.local", "password": "errada-errada"}

    assert cliente.post("/api/auth/jwt/login", data=dados).status_code == 400
    assert cliente.post("/api/auth/jwt/login", data=dados).status_code == 429


@pytest.mark.anyio
async def test_cadastro_com_senha_curta_e_recusado(
    async_db_session_factory, cliente_sem_cookies_residuais
):
    with patch("app.core.auth.enviar_notificacao_novo_cadastro"):
        resposta = cliente_sem_cookies_residuais.post(
            "/api/auth/register",
            json={"email": "curta@teste.local", "password": "1234567", "nome": "Curta"},
        )

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["code"] == "REGISTER_INVALID_PASSWORD"


@pytest.mark.anyio
async def test_cadastro_com_senha_contendo_o_email_e_recusado(
    async_db_session_factory, cliente_sem_cookies_residuais
):
    with patch("app.core.auth.enviar_notificacao_novo_cadastro"):
        resposta = cliente_sem_cookies_residuais.post(
            "/api/auth/register",
            json={"email": "ze@teste.local", "password": "xZE@TESTE.LOCALx", "nome": "Zé"},
        )

    assert resposta.status_code == 400
    assert resposta.json()["detail"]["code"] == "REGISTER_INVALID_PASSWORD"


@pytest.mark.anyio
async def test_cadastro_e_limitado_por_ip(
    async_db_session_factory, cliente_sem_cookies_residuais, monkeypatch
):
    monkeypatch.setattr(settings, "limite_cadastro_por_ip", 1)
    cliente = cliente_sem_cookies_residuais

    with patch("app.core.auth.enviar_notificacao_novo_cadastro"):
        primeira = cliente.post(
            "/api/auth/register",
            json={"email": "um@teste.local", "password": "SenhaForte123", "nome": "Um"},
        )
        segunda = cliente.post(
            "/api/auth/register",
            json={"email": "dois@teste.local", "password": "SenhaForte123", "nome": "Dois"},
        )

    assert primeira.status_code == 201
    assert segunda.status_code == 429


@pytest.mark.anyio
async def test_esqueci_a_senha_e_limitado_por_email(
    async_db_session_factory, cliente_sem_cookies_residuais, monkeypatch
):
    monkeypatch.setattr(settings, "limite_esqueci_senha_por_email", 1)
    cliente = cliente_sem_cookies_residuais
    corpo = {"email": "ninguem@teste.local"}

    assert cliente.post("/api/auth/forgot-password", json=corpo).status_code == 202
    assert cliente.post("/api/auth/forgot-password", json=corpo).status_code == 429


def test_consulta_bloqueada_pelo_limite_nao_chama_a_ia(
    client, db_session_factory, logar_usuario, monkeypatch
):
    monkeypatch.setattr(settings, "limite_consulta_por_minuto", 1)
    session = db_session_factory()
    usuario = Usuario(
        nome="Advogada",
        email="adv@x.com",
        hashed_password="x",
        role=RoleUsuario.COMUM,
        status_cadastro=StatusCadastro.APROVADO,
        is_active=True,
    )
    session.add(usuario)
    session.commit()
    session.refresh(usuario)
    session.close()
    logar_usuario(usuario)

    gerar = MagicMock(
        return_value=PlanoConsulta(
            consultas=[
                ConsultaPlanejada(
                    finalidade="listagem",
                    sql=(
                        "SELECT n.id AS nota_id FROM notas n WHERE "
                        "n.cliente_caso_id = :cliente_caso_id AND n.situacao = 'autorizada'"
                    ),
                )
            ],
            resposta_modelo=None,
        )
    )
    monkeypatch.setattr("app.api.routes_consulta.gerar_plano_consulta", gerar)
    corpo = {"pergunta": "liste as notas", "cliente_caso_id": 1}

    assert client.post("/api/consulta", json=corpo).status_code == 200
    assert client.post("/api/consulta", json=corpo).status_code == 429
    assert gerar.call_count == 1


@pytest.mark.anyio
async def test_login_com_content_type_em_maiusculas_continua_limitado_por_email(
    usuario_ativo_factory, cliente_sem_cookies_residuais, monkeypatch
):
    """O Content-Type é do cliente: variar maiúsculas não pode tirar o
    e-mail da contagem (o FastAPI parseia o form do mesmo jeito)."""
    monkeypatch.setattr(settings, "limite_login_por_email", 2)
    await usuario_ativo_factory(email="caixa@teste.local", senha="SenhaForte123")
    cliente = cliente_sem_cookies_residuais

    def tentar():
        return cliente.post(
            "/api/auth/jwt/login",
            content=b"username=caixa%40teste.local&password=errada-errada",
            headers={"Content-Type": "Application/X-WWW-Form-Urlencoded"},
        )

    assert [tentar().status_code for _ in range(3)] == [400, 400, 429]


@pytest.mark.anyio
async def test_esqueci_a_senha_sem_content_type_continua_limitado_por_email(
    async_db_session_factory, cliente_sem_cookies_residuais, monkeypatch
):
    monkeypatch.setattr(settings, "limite_esqueci_senha_por_email", 1)
    cliente = cliente_sem_cookies_residuais
    corpo = b'{"email": "semtipo@teste.local"}'

    respostas = [
        cliente.post("/api/auth/forgot-password", content=corpo).status_code for _ in range(2)
    ]

    assert respostas == [202, 429]
