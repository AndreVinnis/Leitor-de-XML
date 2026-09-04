"""Tela 04 - Normalização de Produtos."""
import streamlit as st

from api_client import (
    ErroApi,
    confirmar_sugestao,
    confirmar_sugestoes_lote,
    disparar_normalizacao,
    listar_canonicos,
    listar_sugestoes,
    rejeitar_sugestao,
    rejeitar_sugestoes_lote,
    status_normalizacao,
)

# Rótulo exibido na aba -> valor de StatusRevisao esperado por
# GET /api/produtos/sugestoes ("todos" é um valor especial da rota que
# remove o filtro por status, não um membro do enum).
# st.radio seleciona o primeiro item por padrão -- "Pendentes" vem primeiro
# para ser a aba inicial (é o que sobra pra revisar), e "Todos" por último.
ABAS_STATUS = {
    "Pendentes": "pendente",
    "Aprovados": "confirmado",
    "Rejeitados": "rejeitado",
    "Todos": "todos",
}

LIMITE_SUGESTOES = 20


def exibir() -> None:
    st.title("Normalização de Produtos")

    caso_id = st.session_state.get("caso_atual_id")
    if caso_id is None:
        st.warning("Selecione ou crie um cliente/caso na barra lateral para continuar.")
        return

    _exibir_disparo(caso_id)
    st.divider()
    _exibir_lista(caso_id)


def _exibir_disparo(caso_id: int) -> None:
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Normalizar produtos pendentes"):
            try:
                resultado = disparar_normalizacao(caso_id)
                st.session_state["normalizacao_task_id"] = resultado["task_id"]
                st.success("Normalização disparada em segundo plano (via Celery/IA).")
            except ErroApi as erro:
                st.error(f"Erro ao disparar normalização: {erro.detalhe}")

    task_id = st.session_state.get("normalizacao_task_id")
    if task_id:
        with col2:
            if st.button("Consultar status da normalização"):
                try:
                    status = status_normalizacao(task_id)
                    st.info(f"Task {task_id}: {status['status']}")
                    if status["resultado"] is not None:
                        st.json(status["resultado"])
                except ErroApi as erro:
                    st.error(f"Erro ao consultar status: {erro.detalhe}")


def _exibir_lista(caso_id: int) -> None:
    # Mensagens de sucesso/erro das ações de revisão são guardadas em
    # session_state antes do st.rerun() (ver _executar_acao_unitaria/lote) --
    # sem isso, o rerun descarta o st.success/st.error antes de ser exibido
    # e o usuário clica no botão sem ver nenhum retorno. Exibidas aqui, no
    # topo da tela, e removidas em seguida para não reaparecer nos reruns
    # seguintes (ex.: paginação, troca de filtro).
    mensagens_pendentes = st.session_state.pop("mensagens_revisao", [])
    for nivel, texto in mensagens_pendentes:
        if nivel == "sucesso":
            st.success(texto)
        else:
            st.error(texto)

    aba_escolhida = st.radio("Status", list(ABAS_STATUS.keys()), horizontal=True)
    status_api = ABAS_STATUS[aba_escolhida]

    try:
        canonicos = listar_canonicos(caso_id)
    except ErroApi as erro:
        st.error(f"Erro ao carregar categorias: {erro.detalhe}")
        canonicos = []
    categorias = sorted({c["categoria"] for c in canonicos if c["categoria"]})

    col1, col2, col3 = st.columns(3)
    with col1:
        categoria = st.selectbox(
            "Categoria", [""] + categorias, format_func=lambda v: "Todas" if v == "" else v
        )
    with col2:
        fornecedor = st.text_input("Fornecedor")
    with col3:
        busca = st.text_input("Buscar por descrição")

    # Reseta a paginação sempre que algum filtro muda -- senão um offset
    # alto de um filtro anterior deixaria a lista vazia ao trocar de aba.
    chave_filtro = (status_api, categoria, fornecedor, busca)
    if st.session_state.get("sugestoes_filtro_anterior") != chave_filtro:
        st.session_state["sugestoes_offset"] = 0
        st.session_state["sugestoes_filtro_anterior"] = chave_filtro
    offset = st.session_state.get("sugestoes_offset", 0)

    try:
        resposta = listar_sugestoes(
            caso_id,
            status=status_api,
            categoria=categoria or None,
            fornecedor=fornecedor or None,
            busca=busca or None,
            limit=LIMITE_SUGESTOES,
            offset=offset,
        )
    except ErroApi as erro:
        st.error(f"Erro ao carregar sugestões: {erro.detalhe}")
        return

    itens = resposta["itens"]
    total = resposta["total"]
    st.caption(f"{total} sugestão(ões) no total")

    if not itens:
        st.info("Nenhuma sugestão encontrada com esses filtros.")
        return

    # Um checkbox por linha, com chave estável por id de sugestão -- é o que
    # permite ler, depois do rerun disparado por qualquer widget da tela,
    # quais linhas estão marcadas (o Streamlit guarda o valor de um widget
    # com "key" em st.session_state[key] entre reruns).
    for item in itens:
        st.session_state.setdefault(f"sel_{item['id']}", False)
    ids_selecionados = [item["id"] for item in itens if st.session_state.get(f"sel_{item['id']}")]

    # Só entram na seleção em massa as sugestões ainda "pendente" -- as já
    # revisadas seguem a mesma regra dos botões ✓/✕ individuais (desabilitados
    # nessas linhas), então marcá-las aqui só geraria ruído no lote.
    ids_pendentes_pagina = [item["id"] for item in itens if item["status"] == "pendente"]

    st.markdown(f"**{len(ids_selecionados)} selecionado(s)**")
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        if st.button(
            "Selecionar todos",
            disabled=not ids_pendentes_pagina,
            help="Seleciona todas as sugestões pendentes desta página",
        ):
            for item_id in ids_pendentes_pagina:
                st.session_state[f"sel_{item_id}"] = True
            st.rerun()
    with col_sel2:
        if st.button("Limpar seleção", disabled=not ids_selecionados):
            for item_id in ids_selecionados:
                st.session_state[f"sel_{item_id}"] = False
            st.rerun()

    col_lote1, col_lote2 = st.columns(2)
    with col_lote1:
        if st.button("Confirmar selecionados", disabled=not ids_selecionados):
            _executar_acao_lote(confirmar_sugestoes_lote, ids_selecionados)
    with col_lote2:
        if st.button("Rejeitar selecionados", disabled=not ids_selecionados):
            _executar_acao_lote(rejeitar_sugestoes_lote, ids_selecionados)

    st.divider()

    # Montada com st.columns linha a linha, e não st.dataframe: os botões
    # ✓/✕ por linha precisam disparar as rotas UNITÁRIAS de revisão, e uma
    # tabela sem widget não comporta um botão por célula. Os botões de ação
    # em lote acima exercitam as rotas de LOTE -- cobrir os dois caminhos é
    # o objetivo desta tela.
    cabecalho = st.columns([0.5, 3, 2, 1.5, 1, 1, 0.6, 0.6])
    for coluna, titulo in zip(
        cabecalho,
        ["", "Descrição original", "Nome canônico", "Categoria", "Confiança", "Status", "", ""],
    ):
        coluna.markdown(f"**{titulo}**")

    for item in itens:
        linha = st.columns([0.5, 3, 2, 1.5, 1, 1, 0.6, 0.6])
        linha[0].checkbox("", key=f"sel_{item['id']}", label_visibility="collapsed")
        linha[1].write(item["descricao_original"])
        linha[2].write(item["nome_canonico"])
        linha[3].write(item["categoria"] or "--")
        linha[4].write(f"{item['confianca']:.0%}")
        linha[5].write(item["status"])
        # Sugestão já revisada (confirmada ou rejeitada) não deve ser
        # revisada de novo -- os botões ficam desabilitados, mas visíveis,
        # para não desalinhar as colunas das demais linhas.
        ja_revisada = item["status"] != "pendente"
        if linha[6].button(
            "✓", key=f"confirmar_{item['id']}", help="Confirmar sugestão", disabled=ja_revisada
        ):
            _executar_acao_unitaria(confirmar_sugestao, item["id"])
        if linha[7].button(
            "✕", key=f"rejeitar_{item['id']}", help="Rejeitar sugestão", disabled=ja_revisada
        ):
            _executar_acao_unitaria(rejeitar_sugestao, item["id"])

    col_prev, col_next = st.columns(2)
    with col_prev:
        if offset > 0 and st.button("Página anterior", key="sug_prev"):
            st.session_state["sugestoes_offset"] = max(0, offset - LIMITE_SUGESTOES)
            st.rerun()
    with col_next:
        if offset + LIMITE_SUGESTOES < total and st.button("Próxima página", key="sug_next"):
            st.session_state["sugestoes_offset"] = offset + LIMITE_SUGESTOES
            st.rerun()


def _registrar_mensagem(nivel: str, texto: str) -> None:
    """Guarda a mensagem em session_state em vez de chamar st.success/
    st.error diretamente -- o st.rerun() que sempre acontece logo depois
    (para recarregar a lista da API) descartaria a mensagem antes de ela
    aparecer na tela. Ela é lida e exibida no topo de _exibir_lista, no
    próximo ciclo de execução."""
    mensagens = st.session_state.setdefault("mensagens_revisao", [])
    mensagens.append((nivel, texto))


def _executar_acao_unitaria(funcao, sugestao_id: int) -> None:
    """As rotas unitárias de revisão devolvem HTTP 200 mesmo quando a
    sugestão não existe -- o corpo é que diz {"status": "erro", "motivo":
    ...} nesse caso. Por isso o código HTTP nunca é suficiente aqui: sempre
    inspecionamos o campo "status" do retorno."""
    try:
        resultado = funcao(sugestao_id)
    except ErroApi as erro:
        _registrar_mensagem("erro", f"Erro de comunicação com a API: {erro.detalhe}")
        st.rerun()
        return

    if resultado["status"] == "erro":
        _registrar_mensagem(
            "erro", f"Falha ao processar sugestão {sugestao_id}: {resultado.get('motivo', 'motivo desconhecido')}"
        )
    else:
        _registrar_mensagem("sucesso", f"Sugestão {sugestao_id} processada com sucesso.")
    st.rerun()


def _executar_acao_lote(funcao, ids: list[int]) -> None:
    """Mesma lógica da unitária, mas sobre {"resultados": [...]} -- um
    elemento por id enviado, cada um podendo ter falhado independentemente
    (ex.: um id inexistente no meio de uma seleção válida)."""
    try:
        resultado = funcao(ids)
    except ErroApi as erro:
        _registrar_mensagem("erro", f"Erro de comunicação com a API: {erro.detalhe}")
        st.rerun()
        return

    resultados = resultado["resultados"]
    falhas = [r for r in resultados if r["status"] == "erro"]
    sucesso = len(resultados) - len(falhas)

    if sucesso:
        _registrar_mensagem("sucesso", f"{sucesso} sugestão(ões) processada(s) com sucesso.")
    for falha in falhas:
        _registrar_mensagem(
            "erro", f"Sugestão {falha.get('sugestao_id', '?')}: {falha.get('motivo', 'motivo desconhecido')}"
        )
    st.rerun()
