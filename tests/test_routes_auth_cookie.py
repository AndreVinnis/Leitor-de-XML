"""
Cobre o transporte de cookie de verdade (app/core/auth.py::cookie_backend),
algo que nenhum teste exercitava antes -- as rotas de negócio sobrescrevem
usuario_atual_ativo via dependency_overrides (ver tests/conftest.py), então
login/logout/CSRF/sessão deslizante nunca passavam por uma requisição HTTP
real. fastapi-users exige AsyncSession (get_async_session, que numa app real
aponta pro MySQL via asyncmy) -- aqui é sqlite+aiosqlite em memória, só para
isto.
"""
from unittest.mock import patch

import pytest
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import generate_jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import UserManager
from app.core.config import settings
from app.core.database import Base, get_async_session
from app.models.models import StatusCadastro, Usuario
from app.schemas.usuario import UsuarioCreate

HEADER_ANTI_CSRF = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
async def async_db_session_factory():
    from app.main import app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conexao:
        await conexao.run_sync(Base.metadata.create_all)

    fabrica = async_sessionmaker(engine, expire_on_commit=False)

    async def _override():
        async with fabrica() as sessao:
            yield sessao

    app.dependency_overrides[get_async_session] = _override
    yield fabrica
    app.dependency_overrides.pop(get_async_session, None)
    await engine.dispose()


@pytest.fixture
def usuario_ativo_factory(async_db_session_factory):
    async def _criar(email="usuaria@teste.local", senha="SenhaForte123", nome="Usuária Teste"):
        async with async_db_session_factory() as sessao:
            user_db = SQLAlchemyUserDatabase(sessao, Usuario)
            gerenciador = UserManager(user_db)
            with patch("app.core.auth.enviar_notificacao_novo_cadastro"):
                usuario = await gerenciador.create(
                    UsuarioCreate(email=email, password=senha, nome=nome), safe=True
                )
            usuario.is_active = True
            usuario.status_cadastro = StatusCadastro.APROVADO
            sessao.add(usuario)
            await sessao.commit()
            await sessao.refresh(usuario)
            return usuario

    return _criar


@pytest.fixture
def cliente_sem_cookies_residuais(client):
    """`client` é scope="session" (ver conftest.py) -- sem limpar o jar de
    cookies no teardown, o cookie de sessão setado por um teste vazaria para
    o próximo que reusa o mesmo TestClient."""
    yield client
    client.cookies.clear()


@pytest.mark.anyio
async def test_login_por_cookie_204_sem_corpo_e_cookie_httponly(
    usuario_ativo_factory, cliente_sem_cookies_residuais
):
    await usuario_ativo_factory(email="ana@teste.local", senha="SenhaForte123")

    resposta = cliente_sem_cookies_residuais.post(
        "/api/auth/cookie/login",
        data={"username": "ana@teste.local", "password": "SenhaForte123"},
        headers=HEADER_ANTI_CSRF,
    )

    assert resposta.status_code == 204
    assert resposta.content == b""
    set_cookie = resposta.headers.get("set-cookie", "")
    assert "sessao_nfe=" in set_cookie
    assert "httponly" in set_cookie.lower()


@pytest.mark.anyio
async def test_login_por_cookie_sem_header_anti_csrf_e_rejeitado(
    usuario_ativo_factory, cliente_sem_cookies_residuais
):
    await usuario_ativo_factory(email="bruna@teste.local", senha="SenhaForte123")

    resposta = cliente_sem_cookies_residuais.post(
        "/api/auth/cookie/login",
        data={"username": "bruna@teste.local", "password": "SenhaForte123"},
    )

    assert resposta.status_code == 403
    assert "set-cookie" not in resposta.headers


@pytest.mark.anyio
async def test_cookie_autentica_rota_protegida_e_logout_invalida(
    usuario_ativo_factory, cliente_sem_cookies_residuais
):
    await usuario_ativo_factory(email="carla@teste.local", senha="SenhaForte123")

    login = cliente_sem_cookies_residuais.post(
        "/api/auth/cookie/login",
        data={"username": "carla@teste.local", "password": "SenhaForte123"},
        headers=HEADER_ANTI_CSRF,
    )
    assert login.status_code == 204

    quem_sou_eu = cliente_sem_cookies_residuais.get("/api/auth/users/me")
    assert quem_sou_eu.status_code == 200
    assert quem_sou_eu.json()["email"] == "carla@teste.local"

    logout = cliente_sem_cookies_residuais.post(
        "/api/auth/cookie/logout", headers=HEADER_ANTI_CSRF
    )
    assert logout.status_code == 204

    apos_logout = cliente_sem_cookies_residuais.get("/api/auth/users/me")
    assert apos_logout.status_code == 401


@pytest.mark.anyio
async def test_rota_que_muda_estado_via_cookie_sem_header_anti_csrf_e_rejeitada(
    usuario_ativo_factory, cliente_sem_cookies_residuais
):
    await usuario_ativo_factory(email="dora@teste.local", senha="SenhaForte123")
    login = cliente_sem_cookies_residuais.post(
        "/api/auth/cookie/login",
        data={"username": "dora@teste.local", "password": "SenhaForte123"},
        headers=HEADER_ANTI_CSRF,
    )
    assert login.status_code == 204

    resposta = cliente_sem_cookies_residuais.patch(
        "/api/auth/users/me",
        json={"nome": "Dora Editada"},
    )
    assert resposta.status_code == 403

    resposta_com_header = cliente_sem_cookies_residuais.patch(
        "/api/auth/users/me",
        json={"nome": "Dora Editada"},
        headers=HEADER_ANTI_CSRF,
    )
    assert resposta_com_header.status_code == 200


@pytest.mark.anyio
async def test_sessao_desliza_quando_passa_da_metade_da_vida(
    usuario_ativo_factory, cliente_sem_cookies_residuais, monkeypatch
):
    usuario = await usuario_ativo_factory(email="elis@teste.local", senha="SenhaForte123")
    monkeypatch.setattr(settings, "cookie_max_age_segundos", 100)

    token_quase_vencido = generate_jwt(
        {"sub": str(usuario.id), "aud": ["fastapi-users:auth"]},
        settings.secret_key,
        10,  # 10s restantes num cookie cuja vida total configurada é 100s
    )
    cliente_sem_cookies_residuais.cookies.set("sessao_nfe", token_quase_vencido)

    resposta = cliente_sem_cookies_residuais.get("/api/auth/users/me")

    assert resposta.status_code == 200
    novo_cookie = resposta.cookies.get("sessao_nfe")
    assert novo_cookie is not None
    assert novo_cookie != token_quase_vencido


@pytest.mark.anyio
async def test_sessao_nao_desliza_na_primeira_metade_da_vida(
    usuario_ativo_factory, cliente_sem_cookies_residuais, monkeypatch
):
    usuario = await usuario_ativo_factory(email="fabia@teste.local", senha="SenhaForte123")
    monkeypatch.setattr(settings, "cookie_max_age_segundos", 100)

    token_recem_emitido = generate_jwt(
        {"sub": str(usuario.id), "aud": ["fastapi-users:auth"]},
        settings.secret_key,
        90,  # 90s restantes de 100s -- bem dentro da primeira metade
    )
    cliente_sem_cookies_residuais.cookies.set("sessao_nfe", token_recem_emitido)

    resposta = cliente_sem_cookies_residuais.get("/api/auth/users/me")

    assert resposta.status_code == 200
    assert "set-cookie" not in resposta.headers
