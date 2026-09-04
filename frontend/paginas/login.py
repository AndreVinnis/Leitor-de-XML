"""Tela 01 - Login."""
import streamlit as st

from api_client import ErroApi, esqueci_senha, login as api_login, obter_usuario_atual


def exibir() -> None:
    st.title("Bem-vindo de volta")
    st.caption("Acesse sua conta para continuar")

    with st.form("form_login"):
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar")

    if entrar:
        if not email or not senha:
            st.error("Informe e-mail e senha.")
        else:
            try:
                resultado = api_login(email, senha)
                st.session_state["token"] = resultado["access_token"]
                # Busca nome/role logo após autenticar -- é o que alimenta a
                # top bar da sidebar em todas as telas seguintes.
                st.session_state["usuario"] = obter_usuario_atual()
                st.session_state["pagina"] = "dashboard"
                st.rerun()
            except ErroApi as erro:
                if erro.status_code == 400:
                    # LOGIN_BAD_CREDENTIALS cobre tanto senha errada quanto
                    # cadastro ainda pendente de aprovação (is_active=False)
                    # -- sem esse aviso explícito, o teste manual vira um
                    # beco sem saída para quem acabou de se cadastrar.
                    st.error(
                        "E-mail ou senha inválidos. Se você acabou de criar a conta, "
                        "ela pode ainda estar pendente de aprovação por um "
                        "administrador: um cadastro pendente falha com essa mesma "
                        "mensagem, como se a senha estivesse errada."
                    )
                else:
                    st.error(f"Erro ao entrar: {erro.detalhe}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Criar conta"):
            st.session_state["pagina"] = "criar_conta"
            st.rerun()
    with col2:
        with st.expander("Esqueci minha senha"):
            email_recuperacao = st.text_input("E-mail cadastrado", key="email_recuperacao")
            if st.button("Enviar link de redefinição", key="btn_recuperacao"):
                try:
                    esqueci_senha(email_recuperacao)
                    # A API sempre devolve 202 vazio aqui, exista ou não o
                    # e-mail -- a mensagem de sucesso é fixa de propósito.
                    st.success(
                        "Se o e-mail existir na base, um link de redefinição foi "
                        "enviado (confira o MailHog em desenvolvimento)."
                    )
                except ErroApi as erro:
                    st.error(f"Erro ao solicitar redefinição: {erro.detalhe}")
