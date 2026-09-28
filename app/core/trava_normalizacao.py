"""
Trava por caso contra execuções concorrentes de
app/workers/tasks.py::normalizar_produtos_pendentes.

Sem ela, dois disparos para o mesmo cliente_caso_id (duplo clique, F5 no
meio do processamento) enxergam os mesmos itens pendentes e criam sugestões
duplicadas -- não existe unicidade em sugestoes_normalizacao.item_nota_id.

Uma chave no Redis (o mesmo que já serve de broker) por caso, com o task_id
dono como valor e TTL: se o worker morrer no meio, a trava expira sozinha em
vez de travar o caso para sempre. A task renova o TTL antes de cada
tentativa de lote e confere a posse logo antes de cada commit.
Renovar/liberar só agem se o valor ainda for o task_id de quem chama
(compare-and-set via Lua), para uma execução cuja trava já expirou nunca
apagar a trava de outra.
"""

from typing import Optional

import redis

from app.core.config import settings

# Renovada antes de cada tentativa de lote e logo antes de cada commit
# (app/workers/tasks.py::_executar_com_tentativas), então só precisa cobrir
# uma tentativa: chamada ao Claude limitada a 300s
# (normalizador_produtos._TIMEOUT_SEGUNDOS) + embeddings dos canônicos novos
# + a maior espera entre tentativas (30s).
TTL_TRAVA = 900

_SCRIPT_RENOVAR = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""

_SCRIPT_LIBERAR = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

_redis: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _chave(cliente_caso_id: int) -> str:
    return f"normalizacao:caso:{cliente_caso_id}"


def adquirir(cliente_caso_id: int, task_id: str) -> bool:
    """True se a trava foi obtida; False se já há normalização em andamento."""
    return bool(_get_redis().set(_chave(cliente_caso_id), task_id, nx=True, ex=TTL_TRAVA))


def task_em_andamento(cliente_caso_id: int) -> Optional[str]:
    """task_id da normalização em andamento para o caso, ou None."""
    return _get_redis().get(_chave(cliente_caso_id))


def renovar(cliente_caso_id: int, task_id: str) -> bool:
    """Estende o TTL. False se a trava não pertence mais a `task_id`."""
    return bool(
        _get_redis().eval(_SCRIPT_RENOVAR, 1, _chave(cliente_caso_id), task_id, TTL_TRAVA)
    )


def liberar(cliente_caso_id: int, task_id: str) -> None:
    _get_redis().eval(_SCRIPT_LIBERAR, 1, _chave(cliente_caso_id), task_id)
