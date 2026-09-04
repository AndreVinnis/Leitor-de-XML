"""Tela 03 - Home (Dashboard)."""
import streamlit as st

from api_client import (
    ErroApi,
    listar_notas,
    obter_estatisticas,
    progresso_lote,
    upload_notas,
)

# GET /api/notas só aceita valores do enum StatusProcessamento -- um valor
# fora disso estoura 500 no backend (a rota não trata ValueError como
# /produtos/sugestoes trata). "" representa "sem filtro" só no front.
STATUS_NOTAS = ["", "pendente", "sucesso", "erro", "duplicado"]

LIMITE_NOTAS = 20


def exibir() -> None:
    st.title("Dashboard")

    caso_id = st.session_state.get("caso_atual_id")
    if caso_id is None:
        st.warning("Selecione ou crie um cliente/caso na barra lateral para continuar.")
        return

    _exibir_cards(caso_id)
    st.divider()
    _exibir_upload(caso_id)
    st.divider()
    _exibir_progresso_lote()
    st.divider()
    _exibir_notas_recentes(caso_id)


def _exibir_cards(caso_id: int) -> None:
    try:
        stats = obter_estatisticas(caso_id)
    except ErroApi as erro:
        st.error(f"Erro ao carregar estatísticas: {erro.detalhe}")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Notas processadas", stats["notas_processadas"])
    col2.metric("Pendentes", stats["pendentes"])
    col3.metric("Erros", stats["erros"])


def _exibir_upload(caso_id: int) -> None:
    st.subheader("Upload de notas")
    cnpj_cliente = st.text_input("CNPJ do cliente (só números)", key="cnpj_upload")
    arquivos = st.file_uploader(
        "Arraste arquivos XML aqui ou clique para selecionar",
        type=["xml"],
        accept_multiple_files=True,
    )

    if st.button("Enviar lote"):
        if not cnpj_cliente:
            st.error("Informe o CNPJ do cliente.")
        elif not arquivos:
            st.error("Selecione ao menos um arquivo XML.")
        else:
            try:
                dados = [(arquivo.name, arquivo.getvalue()) for arquivo in arquivos]
                resultado = upload_notas(caso_id, cnpj_cliente, dados)
                st.session_state["lote_id"] = resultado["lote_id"]
                st.success(
                    f"Lote enviado: {resultado['total_arquivos']} arquivo(s) em "
                    "processamento. Acompanhe o progresso abaixo."
                )
                st.rerun()
            except ErroApi as erro:
                st.error(f"Erro no upload: {erro.detalhe}")


def _exibir_progresso_lote() -> None:
    lote_id = st.session_state.get("lote_id")
    if not lote_id:
        return

    st.subheader("Progresso do último lote enviado")
    if st.button("Atualizar"):
        st.rerun()

    try:
        progresso = progresso_lote(lote_id)
    except ErroApi as erro:
        st.error(f"Erro ao consultar o lote: {erro.detalhe}")
        return

    st.write(
        f"{progresso['concluidos']} de {progresso['total_arquivos']} concluído(s) "
        f"-- {progresso['com_erro']} com erro."
    )
    # Lista arquivo a arquivo com o motivo_erro: é o que torna visível a
    # falha de parsing de um XML específico, que o badge de status por nota
    # sozinho não explica (o item nunca chega a virar Nota nesse caso).
    for arquivo in progresso["arquivos"]:
        linha = f"- **{arquivo['nome_arquivo']}**: {arquivo['status']}"
        if arquivo["motivo_erro"]:
            linha += f" -- {arquivo['motivo_erro']}"
        st.markdown(linha)


def _exibir_notas_recentes(caso_id: int) -> None:
    st.subheader("Notas recentes")

    status_escolhido = st.selectbox(
        "Filtrar por status",
        STATUS_NOTAS,
        format_func=lambda v: "Todos" if v == "" else v.capitalize(),
    )

    # Reseta a paginação sempre que o filtro muda -- senão um offset alto de
    # um filtro anterior deixaria a lista vazia ao trocar de status.
    if st.session_state.get("notas_filtro_anterior") != status_escolhido:
        st.session_state["notas_offset"] = 0
        st.session_state["notas_filtro_anterior"] = status_escolhido
    offset = st.session_state.get("notas_offset", 0)

    try:
        resposta = listar_notas(
            caso_id, status=status_escolhido or None, limit=LIMITE_NOTAS, offset=offset
        )
    except ErroApi as erro:
        st.error(f"Erro ao carregar notas: {erro.detalhe}")
        return

    itens = resposta["itens"]
    total = resposta["total"]
    st.caption(f"{total} nota(s) no total")

    if not itens:
        st.info("Nenhuma nota encontrada com esse filtro.")
        return

    st.dataframe(
        itens,
        use_container_width=True,
        hide_index=True,
        column_order=["numero", "emitente_nome", "data_emissao", "valor_total", "status"],
    )

    col_prev, col_next = st.columns(2)
    with col_prev:
        if offset > 0 and st.button("Página anterior", key="notas_prev"):
            st.session_state["notas_offset"] = max(0, offset - LIMITE_NOTAS)
            st.rerun()
    with col_next:
        if offset + LIMITE_NOTAS < total and st.button("Próxima página", key="notas_next"):
            st.session_state["notas_offset"] = offset + LIMITE_NOTAS
            st.rerun()
