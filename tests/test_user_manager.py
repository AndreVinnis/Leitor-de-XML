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
