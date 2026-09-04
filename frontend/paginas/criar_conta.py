"""Tela 02 - Criar Conta."""
import streamlit as st

from api_client import ErroApi, registrar


def _extrair_codigo_erro(detalhe) -> str | None:
    """A resposta de erro do fastapi-users vem como {"detail": "CODIGO"}
    para a maioria dos casos (ex.: REGISTER_USER_ALREADY_EXISTS) ou
    {"detail": {"code": "CODIGO", "reason": ...}} para senha inválida
    (REGISTER_INVALID_PASSWORD, com o motivo da validação junto)."""
    if not isinstance(detalhe, dict):
        return None
    interno = detalhe.get("detail")
    if isinstance(interno, str):
        return interno
    if isinstance(interno, dict):
        return interno.get("code")
    return None


def exibir() -> None:
    st.title("Criar conta")
    st.caption("Acesse sua conta para continuar")

    with st.form("form_criar_conta"):
        nome = st.text_input("Nome completo")
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        confirmacao = st.text_input("Confirmar senha", type="password")
        criar = st.form_submit_button("Criar conta")

    if criar:
        if not nome or not email or not senha:
            st.error("Preencha todos os campos.")
        elif senha != confirmacao:
            # Confirmação validada só no cliente, igual ao protótipo do
            # Figma -- a API nem recebe esse campo (schema UsuarioCreate não
            # tem "confirmar_senha").
            st.error("As senhas não conferem.")
        else:
            try:
                registrar(email, senha, nome)
                st.success("Conta criada com sucesso!")
                # A resposta da API traz is_active=true, mas
                # on_after_register desliga isso logo em seguida (ver
                # app/core/auth.py) -- por isso não exibimos esse campo
                # aqui, seria enganoso mostrar "ativo" e o login falhar.
                st.info(
                    "O cadastro nasce inativo: um administrador precisa aprová-lo "
                    "pelo link enviado por e-mail antes que você consiga entrar. "
                    "Em ambiente de desenvolvimento, esse e-mail cai no MailHog "
                    "(http://localhost:8025), não numa caixa de entrada real."
                )
            except ErroApi as erro:
                codigo = _extrair_codigo_erro(erro.detalhe)
                if codigo == "REGISTER_USER_ALREADY_EXISTS":
                    st.error("Já existe uma conta cadastrada com esse e-mail.")
                elif codigo == "REGISTER_INVALID_PASSWORD":
                    st.error("Senha inválida: verifique os requisitos mínimos de segurança.")
                else:
                    st.error(f"Erro ao criar conta: {erro.detalhe}")

    st.divider()
    if st.button("Já tenho conta -- fazer login"):
        st.session_state["pagina"] = "login"
        st.rerun()
