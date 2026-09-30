"""
Limite de tentativas por janela fixa, guardado no Redis (o mesmo do broker e
de app/core/trava_normalizacao.py).

Protege as rotas que custam caro ou que são alvo de força bruta: login
(senha), esqueci-a-senha e cadastro (disparam e-mail), consulta NL->SQL e
normalização (cada chamada vai para a IA e custa dinheiro). Cada regra é uma
dependência FastAPI que conta a requisição numa chave
`limite:<nome>:<identificador>` com TTL igual à janela; passou do máximo,
devolve 429 com Retry-After.

Fail-open, de propósito: se o Redis estiver fora, a requisição passa e o
erro vai para o log. Uma queda de infra não pode travar o login do
escritório inteiro -- e sem Redis o Celery já não funciona, então o problema
aparece de qualquer jeito.

O identificador por IP depende de o uvicorn enxergar o IP real do cliente
atrás do proxy do Vite (`--proxy-headers --forwarded-allow-ips` com o IP
fixo do container `web`, ver docker-compose.yml). Se essa configuração
quebrar, todos os usuários do React caem no mesmo balde de IP e o limite por
IP de login/cadastro vira um bloqueio do escritório inteiro -- é por isso que
os tetos por IP são bem mais altos que os por e-mail. As chaves por e-mail e
por IP se somam (a requisição precisa passar nas duas).
"""

import hashlib
import json
import logging
from typing import Awaitable, Callable, Optional

import redis
from fastapi import Depends, HTTPException, Request, status

from app.core.auth import usuario_atual_ativo
from app.core.config import settings
from app.models.models import Usuario

logger = logging.getLogger(__name__)

# INCR + EXPIRE atômicos: a janela começa na primeira requisição e o TTL
# nunca é renovado pelas seguintes (janela fixa, não deslizante).
_SCRIPT_INCREMENTAR = """
local n = redis.call('incr', KEYS[1])
if n == 1 then
    redis.call('expire', KEYS[1], ARGV[1])
end
return {n, redis.call('ttl', KEYS[1])}
"""

_redis: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_timeout=2
        )
    return _redis


def _incrementar(chave: str, janela_s: int) -> tuple[int, int]:
    """Soma 1 na chave e devolve (contagem na janela, segundos até zerar)."""
    contagem, ttl = _get_redis().eval(_SCRIPT_INCREMENTAR, 1, chave, janela_s)
    return int(contagem), int(ttl)


def verificar(chave: str, maximo: int, janela_s: int) -> None:
    """Conta uma requisição em `chave`; 429 se passar de `maximo` na janela."""
    try:
        contagem, ttl = _incrementar(chave, janela_s)
    except (redis.RedisError, OSError) as exc:
        logger.warning("Limite de tentativas indisponível (%s): %r", chave, exc)
        return
    if contagem > maximo:
        espera = ttl if ttl > 0 else janela_s
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Muitas tentativas em pouco tempo. "
                f"Tente de novo em {max(1, round(espera / 60))} minuto(s)."
            ),
            headers={"Retry-After": str(espera)},
        )


def _anonimizar(valor: str) -> str:
    # A chave fica no Redis; não há motivo para guardar e-mail em claro lá.
    return hashlib.sha256(valor.strip().lower().encode()).hexdigest()[:32]


async def _ip_do_cliente(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _email_da_requisicao(request: Request) -> Optional[str]:
    """
    E-mail do form de login (`username`, OAuth2PasswordRequestForm) ou do
    JSON de esqueci-a-senha/cadastro (`email`).

    Decide pelo caminho, nunca pelo Content-Type: o header é do cliente, e
    variar maiúsculas ou omiti-lo fazia o FastAPI ainda parsear o corpo
    enquanto esta função não achava e-mail nenhum -- e sem e-mail não havia
    limite por e-mail. O FastAPI já leu o corpo antes das dependências, e o
    Starlette guarda o form/corpo no próprio Request.
    """
    try:
        if request.url.path.endswith("/login"):
            valor = (await request.form()).get("username")
        else:
            corpo = json.loads(await request.body() or b"null")
            valor = corpo.get("email") if isinstance(corpo, dict) else None
    except Exception:
        # Corpo malformado: a própria rota devolve 422. Sem e-mail, sobra o
        # limite por IP.
        return None
    return _anonimizar(valor) if isinstance(valor, str) and valor.strip() else None


def _limitar(
    nome: str,
    maximo: Callable[[], int],
    janela_s: int,
    identificar: Callable[[Request], Awaitable[Optional[str]]],
    sufixo_caminho: Optional[str] = None,
):
    """
    Fábrica de dependência. `maximo` é lido na hora (lambda sobre settings)
    para os testes conseguirem baixar o teto via monkeypatch. Com
    `sufixo_caminho`, só conta requisições cujo caminho termina nele -- usado
    quando a dependência vai num include_router do fastapi-users que também
    traz rotas que não devem contar (ex.: /logout junto de /login).
    """

    async def dependencia(request: Request) -> None:
        if sufixo_caminho and not request.url.path.endswith(sufixo_caminho):
            return
        identificador = await identificar(request)
        if identificador is None:
            return
        verificar(f"limite:{nome}:{identificador}", maximo(), janela_s)

    return dependencia


def _limitar_por_usuario(nome: str, maximo: Callable[[], int], janela_s: int):
    async def dependencia(usuario: Usuario = Depends(usuario_atual_ativo)) -> None:
        verificar(f"limite:{nome}:{usuario.id}", maximo(), janela_s)

    return dependencia


_15_MIN = 15 * 60
_1_HORA = 60 * 60
_1_DIA = 24 * 60 * 60

login_por_email = _limitar(
    "login_email", lambda: settings.limite_login_por_email, _15_MIN, _email_da_requisicao, "/login"
)
login_por_ip = _limitar(
    "login_ip", lambda: settings.limite_login_por_ip, _15_MIN, _ip_do_cliente, "/login"
)
esqueci_senha_por_email = _limitar(
    "senha_email",
    lambda: settings.limite_esqueci_senha_por_email,
    _1_HORA,
    _email_da_requisicao,
    "/forgot-password",
)
esqueci_senha_por_ip = _limitar(
    "senha_ip",
    lambda: settings.limite_esqueci_senha_por_ip,
    _1_HORA,
    _ip_do_cliente,
    "/forgot-password",
)
cadastro_por_ip = _limitar(
    "cadastro_ip", lambda: settings.limite_cadastro_por_ip, _1_HORA, _ip_do_cliente
)
consulta_por_minuto = _limitar_por_usuario(
    "consulta_min", lambda: settings.limite_consulta_por_minuto, 60
)
consulta_por_dia = _limitar_por_usuario(
    "consulta_dia", lambda: settings.limite_consulta_por_dia, _1_DIA
)
normalizacao_por_hora = _limitar_por_usuario(
    "normalizacao_hora", lambda: settings.limite_normalizacao_por_hora, _1_HORA
)
