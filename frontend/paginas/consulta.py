"""Módulo de Consulta em linguagem natural (RF-005/RF-006)."""
import streamlit as st

from api_client import ErroApi, consultar


def exibir() -> None:
    st.title("Consulta")

    caso_id = st.session_state.get("caso_atual_id")
    if caso_id is None:
        st.warning("Selecione ou crie um cliente/caso na barra lateral para continuar.")
        return

    pergunta = st.text_area(
        "Pergunta",
        placeholder="Ex.: quantas notas de entrada existem para o produto Arroz 5kg?",
    )

    if st.button("Consultar", disabled=not pergunta):
        try:
            resultado = consultar(pergunta, caso_id)
        except ErroApi as erro:
            # A rota devolve 422 com o motivo do bloqueio quando o SQL
            # gerado pela IA reprova na validação de segurança (RNF-003) --
            # isso não é uma falha de comunicação, é a validação funcionando.
            st.error(f"Consulta recusada: {erro.detalhe}")
            return
        st.session_state["consulta_resultado"] = resultado

    resultado = st.session_state.get("consulta_resultado")
    if resultado:
        st.caption(f"{resultado['total_linhas']} linha(s) encontrada(s)")
        if resultado["linhas"]:
            st.dataframe(
                [dict(zip(resultado["colunas"], linha)) for linha in resultado["linhas"]],
                use_container_width=True,
            )
        else:
            st.info("Nenhum resultado para essa pergunta.")

        # SQL sempre visível, nunca escondido atrás de um modo "avançado" --
        # rastreabilidade jurídica (RNF-004): o advogado precisa poder
        # mostrar de onde o número veio.
        with st.expander("SQL gerado"):
            st.code(resultado["sql_gerado"], language="sql")
