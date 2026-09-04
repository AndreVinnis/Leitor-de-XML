from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth import UserManager


class _UsuarioFake:
    id = 42


@pytest.mark.anyio
async def test_on_after_register_desativa_usuario_e_notifica_admins():
    """
    O router de registro do fastapi-users sempre cria o usuário com
    is_active=True (create com safe=True). on_after_register precisa
    desligar isso na marra e enfileirar o e-mail pros admins -- é essa
    regra que garante que ninguém loga sem aprovação.
    """
    user_db = MagicMock()
    user_db.update = AsyncMock()
    manager = UserManager(user_db)
    usuario_fake = _UsuarioFake()

    with patch("app.core.auth.enviar_notificacao_novo_cadastro") as mock_task:
        await manager.on_after_register(usuario_fake)

    user_db.update.assert_awaited_once_with(usuario_fake, {"is_active": False})
    mock_task.delay.assert_called_once_with(42)


@pytest.mark.anyio
async def test_on_after_forgot_password_dispara_task_de_email():
    """
    POST /api/auth/forgot-password (fastapi-users) chama esse hook com o
    token já gerado -- a task só precisa repassar usuario_id + token pro
    worker montar o e-mail (SMTP síncrono não roda na request async).
    """
    user_db = MagicMock()
    manager = UserManager(user_db)
    usuario_fake = _UsuarioFake()

    with patch("app.core.auth.enviar_email_redefinicao_senha") as mock_task:
        await manager.on_after_forgot_password(usuario_fake, "token-abc")

    mock_task.delay.assert_called_once_with(42, "token-abc")
