"""
Cliente HTTP da API para o front-end de teste manual.

Concentra numa função por endpoint todas as armadilhas do contrato da API
que foram levantadas lendo o código das rotas (não a documentação --
`app/api/routes_*.py` é a fonte da verdade). O objetivo é que nenhuma tela
precise saber, por exemplo, que o login é form-urlencoded ou que
`/api/notas` não aceita barra final: elas só chamam a função certa daqui.
"""
import os

import requests
import streamlit as st

# No container do Streamlit, "localhost" é o próprio container -- por isso
# o compose injeta API_BASE_URL=http://api:8000 (nome do serviço na rede do
# Compose) e não reaproveita o valor de .env, que é http://localhost:8000
# (correto só para os links de aprovação clicados no navegador do host).
BASE_URL = os.getenv("API_BASE_URL", "http://api:8000")

TIMEOUT_PADRAO = 15


class ErroApi(Exception):
    """Erro genérico ao chamar a API. Guarda status HTTP e corpo (quando
    houver) para cada tela decidir como traduzir o erro para o usuário."""

    def __init__(self, status_code: int, detalhe):
        self.status_code = status_code
        self.detalhe = detalhe
        super().__init__(f"Erro {status_code} na API: {detalhe}")


def _cabecalhos() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _tratar_resposta(resposta: requests.Response):
    """
    Ponto único de tratamento de resposta -- é aqui que mora o tratamento
    centralizado de 401 exigido pelo plano. O token JWT dura 3600s
    (lifetime_seconds em app/core/auth.py); como uma sessão de teste manual
    tende a ficar bem mais tempo que isso com a mesma aba aberta, um 401 no
    meio do caminho é esperado -- em vez de deixar cada tela lidar com isso
    (e vazar uma stacktrace), aqui a gente já limpa a sessão e manda de
    volta pro login.
    """
    if resposta.status_code == 401:
        st.session_state["token"] = None
        st.session_state["usuario"] = None
        st.session_state["pagina"] = "login"
        st.warning("Sua sessão expirou. Faça login novamente.")
        st.rerun()

    if resposta.status_code >= 400:
        try:
            detalhe = resposta.json()
        except ValueError:
            detalhe = resposta.text
        raise ErroApi(resposta.status_code, detalhe)

    if resposta.status_code == 204 or not resposta.content:
        return None
    return resposta.json()


# --------------------------------------------------------------------------
# Autenticação / cadastro (app/api/routes_auth.py, via fastapi-users)
# --------------------------------------------------------------------------

def login(email: str, senha: str) -> dict:
    """POST /api/auth/jwt/login exige application/x-www-form-urlencoded
    (data=, nunca json=): o campo se chama "username" por padrão do OAuth2
    Password Flow que o fastapi-users implementa, mas o valor esperado é o
    e-mail mesmo -- não existe um "username" separado no modelo Usuario."""
    resposta = requests.post(
        f"{BASE_URL}/api/auth/jwt/login",
        data={"username": email, "password": senha},
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def obter_usuario_atual() -> dict:
    resposta = requests.get(
        f"{BASE_URL}/api/auth/users/me", headers=_cabecalhos(), timeout=TIMEOUT_PADRAO
    )
    return _tratar_resposta(resposta)


def registrar(email: str, senha: str, nome: str) -> dict:
    resposta = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": senha, "nome": nome},
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def esqueci_senha(email: str) -> None:
    """POST /api/auth/forgot-password sempre devolve 202 com corpo vazio,
    mesmo se o e-mail não existir (o fastapi-users não revela se um e-mail
    está cadastrado) -- por isso a mensagem de sucesso na tela é fixa."""
    resposta = requests.post(
        f"{BASE_URL}/api/auth/forgot-password",
        json={"email": email},
        timeout=TIMEOUT_PADRAO,
    )
    _tratar_resposta(resposta)


# --------------------------------------------------------------------------
# Clientes/casos (app/api/routes_casos.py)
# --------------------------------------------------------------------------

def listar_casos() -> list:
    """Sem barra final: a rota é registrada com path "", e /api/casos/ vira
    um redirect 307 que pode derrubar o header Authorization pelo caminho."""
    resposta = requests.get(
        f"{BASE_URL}/api/casos", headers=_cabecalhos(), timeout=TIMEOUT_PADRAO
    )
    return _tratar_resposta(resposta)


def criar_caso(nome_cliente: str, identificacao_caso: str | None = None) -> dict:
    resposta = requests.post(
        f"{BASE_URL}/api/casos",
        json={"nome_cliente": nome_cliente, "identificacao_caso": identificacao_caso},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


# --------------------------------------------------------------------------
# Dashboard (app/api/routes_dashboard.py)
# --------------------------------------------------------------------------

def obter_estatisticas(cliente_caso_id: int) -> dict:
    resposta = requests.get(
        f"{BASE_URL}/api/dashboard/estatisticas",
        params={"cliente_caso_id": cliente_caso_id},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


# --------------------------------------------------------------------------
# Notas / upload (app/api/routes_notas.py, app/api/routes_upload.py)
# --------------------------------------------------------------------------

def listar_notas(
    cliente_caso_id: int,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """GET /api/notas devolve envelope {"itens", "total"} (diferente de
    /api/casos e /api/produtos/canonicos, que devolvem lista nua). status,
    quando informado, PRECISA ser um valor de StatusProcessamento -- a rota
    não trata ValueError e um valor inválido estoura 500, não 400."""
    params = {"cliente_caso_id": cliente_caso_id, "limit": limit, "offset": offset}
    if status:
        params["status"] = status
    resposta = requests.get(
        f"{BASE_URL}/api/notas", params=params, headers=_cabecalhos(), timeout=TIMEOUT_PADRAO
    )
    return _tratar_resposta(resposta)


def upload_notas(cliente_caso_id: int, cnpj_cliente: str, arquivos: list[tuple[str, bytes]]) -> dict:
    """POST /api/notas/upload é multipart/form-data. O campo de arquivos
    tem que se chamar exatamente "arquivos" (list[UploadFile] = File(...)
    na rota), repetido uma vez por arquivo -- "arquivos": arquivos, lista de
    tuplas (nome_do_arquivo, conteudo_em_bytes)."""
    arquivos_multipart = [
        ("arquivos", (nome, conteudo, "text/xml")) for nome, conteudo in arquivos
    ]
    resposta = requests.post(
        f"{BASE_URL}/api/notas/upload",
        data={"cliente_caso_id": cliente_caso_id, "cnpj_cliente": cnpj_cliente},
        files=arquivos_multipart,
        headers=_cabecalhos(),
        timeout=120,  # lote pode ter muitos arquivos; a rota só enfileira, mas a gravação em disco é síncrona
    )
    return _tratar_resposta(resposta)


def progresso_lote(lote_id: str) -> dict:
    resposta = requests.get(
        f"{BASE_URL}/api/notas/lotes/{lote_id}", headers=_cabecalhos(), timeout=TIMEOUT_PADRAO
    )
    return _tratar_resposta(resposta)


# --------------------------------------------------------------------------
# Produtos / normalização (app/api/routes_produtos.py)
# --------------------------------------------------------------------------

def disparar_normalizacao(cliente_caso_id: int) -> dict:
    """Body(..., embed=True) na rota: o corpo tem que ser
    {"cliente_caso_id": N}, nunca o inteiro cru."""
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/normalizar",
        json={"cliente_caso_id": cliente_caso_id},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def status_normalizacao(task_id: str) -> dict:
    resposta = requests.get(
        f"{BASE_URL}/api/produtos/normalizar/{task_id}/status",
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def listar_canonicos(cliente_caso_id: int) -> list:
    """Lista nua (sem envelope), diferente de /api/notas e /sugestoes."""
    resposta = requests.get(
        f"{BASE_URL}/api/produtos/canonicos",
        params={"cliente_caso_id": cliente_caso_id},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def criar_canonico(cliente_caso_id: int, nome_canonico: str, categoria: str | None = None) -> dict:
    """POST /api/produtos/canonicos: cria manualmente um canônico (ex.: opção
    "+ Criar novo" ao corrigir uma sugestão). Devolve o produto criado, com id."""
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/canonicos",
        json={
            "cliente_caso_id": cliente_caso_id,
            "nome_canonico": nome_canonico,
            "categoria": categoria,
        },
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def editar_canonico(
    produto_canonico_id: int, nome_canonico: str | None = None, categoria: str | None = None
) -> dict:
    """PATCH /api/produtos/canonicos/{id}: envia só os campos informados.
    categoria="" limpa o campo; categoria=None significa "não mexer"."""
    resposta = requests.patch(
        f"{BASE_URL}/api/produtos/canonicos/{produto_canonico_id}",
        json={"nome_canonico": nome_canonico, "categoria": categoria},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def corrigir_sugestao(sugestao_id: int, produto_canonico_id: int) -> dict:
    """POST /api/produtos/sugestoes/{id}/corrigir: mesma lógica de "200
    mesmo com erro" das demais rotas de revisão (confirmar/rejeitar)."""
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/sugestoes/{sugestao_id}/corrigir",
        json={"produto_canonico_id": produto_canonico_id},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def listar_sugestoes(
    cliente_caso_id: int,
    status: str = "pendente",
    categoria: str | None = None,
    fornecedor: str | None = None,
    busca: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    params = {"cliente_caso_id": cliente_caso_id, "status": status, "limit": limit, "offset": offset}
    if categoria:
        params["categoria"] = categoria
    if fornecedor:
        params["fornecedor"] = fornecedor
    if busca:
        params["busca"] = busca
    resposta = requests.get(
        f"{BASE_URL}/api/produtos/sugestoes",
        params=params,
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def confirmar_sugestao(sugestao_id: int) -> dict:
    """As 4 rotas de revisão (esta, rejeitar_sugestao e as duas em lote
    abaixo) SEMPRE devolvem HTTP 200, mesmo quando a sugestão não existe --
    o corpo é que carrega {"status": "erro", "motivo": ...} nesse caso.
    _tratar_resposta não filtra isso: quem chama tem que inspecionar o
    campo "status" do retorno."""
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/sugestoes/{sugestao_id}/confirmar",
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def rejeitar_sugestao(sugestao_id: int) -> dict:
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/sugestoes/{sugestao_id}/rejeitar",
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def confirmar_sugestoes_lote(ids: list[int]) -> dict:
    """Body(..., embed=True) também aqui: {"ids": [...]}, nunca a lista
    crua. Retorno: {"resultados": [...]}, um elemento por id, na mesma
    lógica de "200 mesmo com erro" das rotas unitárias."""
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/sugestoes/lote/confirmar",
        json={"ids": ids},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


def rejeitar_sugestoes_lote(ids: list[int]) -> dict:
    resposta = requests.post(
        f"{BASE_URL}/api/produtos/sugestoes/lote/rejeitar",
        json={"ids": ids},
        headers=_cabecalhos(),
        timeout=TIMEOUT_PADRAO,
    )
    return _tratar_resposta(resposta)


# --------------------------------------------------------------------------
# Consulta em linguagem natural (app/api/routes_consulta.py)
# --------------------------------------------------------------------------

def consultar(pergunta: str, cliente_caso_id: int) -> dict:
    """POST /api/consulta devolve 422 (via ErroApi) quando a IA gera um SQL
    que não passa na validação de segurança -- a tela mostra erro.detalhe
    nesse caso, não é uma falha de comunicação. Timeout maior que o padrão
    porque a rota chama o Gemini antes de consultar o banco."""
    resposta = requests.post(
        f"{BASE_URL}/api/consulta",
        json={"pergunta": pergunta, "cliente_caso_id": cliente_caso_id},
        headers=_cabecalhos(),
        timeout=60,
    )
    return _tratar_resposta(resposta)
