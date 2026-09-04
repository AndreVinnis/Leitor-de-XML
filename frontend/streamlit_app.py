"""
Entrada única do front-end de teste manual (Streamlit).

Roteamento próprio via st.session_state, e não o diretório mágico `pages/`
do Streamlit: com `pages/`, o Streamlit gera uma URL por arquivo e qualquer
pessoa navega direto para ela pela barra de endereço, contornando a tela de
login (o framework não protege rotas sozinho). Aqui, cada "página" é só uma
função chamada condicionalmente a partir de main() -- a proteção vem de
nunca chamar a função de uma tela autenticada sem token na sessão.
"""
import streamlit as st

from api_client import ErroApi, criar_caso, listar_casos
from paginas import consulta, criar_conta, dashboard, login, normalizacao

st.set_page_config(
    page_title="Leitor de XML -- Teste de Integração",
    page_icon="📄",
    layout="wide",
)


def _inicializar_sessao() -> None:
    """Garante que todas as chaves usadas pelas telas existam antes do
    primeiro acesso -- evita KeyError espalhado pelas páginas a cada rerun."""
    padrao = {
        "token": None,
        "usuario": None,
        "pagina": "login",
        "caso_atual_id": None,
        "lote_id": None,
    }
    for chave, valor in padrao.items():
        st.session_state.setdefault(chave, valor)


def _sidebar_autenticada() -> None:
    """
    Top bar + navegação + seletor de cliente/caso, comuns a todas as telas
    logadas.

    O seletor de caso vive aqui (e não dentro de cada tela) porque
    cliente_caso_id é obrigatório em upload, estatísticas, notas e
    sugestões, e o protótipo do Figma não desenhou onde essa escolha é
    feita -- sem isso, nenhuma das 4 telas consegue chamar a API de verdade.
    O "+ Novo caso" existe pelo mesmo motivo: um banco vazio, sem nenhum
    caso, travaria o teste de upload logo na largada.
    """
    usuario = st.session_state["usuario"] or {}
    with st.sidebar:
        st.markdown(f"**{usuario.get('nome', '')}**")
        st.caption(str(usuario.get("role", "")))
        st.divider()

        if st.button("Dashboard", use_container_width=True):
            st.session_state["pagina"] = "dashboard"
            st.rerun()
        if st.button("Normalização de Produtos", use_container_width=True):
            st.session_state["pagina"] = "normalizacao"
            st.rerun()
        if st.button("Consulta", use_container_width=True):
            st.session_state["pagina"] = "consulta"
            st.rerun()
        if st.button("Sair", use_container_width=True):
            st.session_state["token"] = None
            st.session_state["usuario"] = None
            st.session_state["pagina"] = "login"
            st.rerun()

        st.divider()
        st.markdown("### Cliente / caso")
        try:
            casos = listar_casos()
        except ErroApi as erro:
            st.error(f"Não foi possível carregar os casos: {erro.detalhe}")
            casos = []

        if casos:
            opcoes = {
                f"{c['nome_cliente']} ({c['identificacao_caso'] or 'sem identificação'})": c["id"]
                for c in casos
            }
            rotulo_escolhido = st.selectbox("Caso ativo", list(opcoes.keys()))
            st.session_state["caso_atual_id"] = opcoes[rotulo_escolhido]
        else:
            st.info("Nenhum caso cadastrado ainda. Crie um abaixo.")
            st.session_state["caso_atual_id"] = None

        with st.expander("+ Novo caso"):
            with st.form("form_novo_caso", clear_on_submit=True):
                nome_cliente = st.text_input("Nome do cliente")
                identificacao = st.text_input("Identificação do caso (opcional)")
                if st.form_submit_button("Criar caso"):
                    if not nome_cliente:
                        st.error("Informe o nome do cliente.")
                    else:
                        try:
                            criar_caso(nome_cliente, identificacao or None)
                            st.success("Caso criado com sucesso.")
                            st.rerun()
                        except ErroApi as erro:
                            st.error(f"Erro ao criar caso: {erro.detalhe}")


def main() -> None:
    _inicializar_sessao()

    if not st.session_state["token"]:
        # Sem token: só as telas públicas existem. A navegação entre elas é
        # feita só por st.session_state["pagina"], nunca por URL.
        if st.session_state["pagina"] == "criar_conta":
            criar_conta.exibir()
        else:
            login.exibir()
        return

    _sidebar_autenticada()

    pagina = st.session_state["pagina"]
    if pagina == "normalizacao":
        normalizacao.exibir()
    elif pagina == "consulta":
        consulta.exibir()
    else:
        dashboard.exibir()


if __name__ == "__main__":
    main()
