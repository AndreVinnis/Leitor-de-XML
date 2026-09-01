from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_SALT = "aprovacao-cadastro"


class TokenInvalido(Exception):
    pass


class TokenExpirado(Exception):
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def gerar_token_aprovacao(admin_id: int, usuario_id: int, acao: str) -> str:
    """Token assinado e com prazo de validade, carregando quem pode decidir
    (admin_id), sobre quem (usuario_id) e qual ação (aprovar/reprovar)."""
    return _serializer().dumps({"admin_id": admin_id, "usuario_id": usuario_id, "acao": acao})


def verificar_token_aprovacao(token: str) -> dict:
    max_age = settings.token_aprovacao_expira_minutos * 60
    try:
        return _serializer().loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise TokenExpirado() from exc
    except BadSignature as exc:
        raise TokenInvalido() from exc
