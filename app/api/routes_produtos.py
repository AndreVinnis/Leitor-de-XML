from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import (
    ItemNota,
    LogAuditoria,
    Nota,
    ProdutoCanonico,
    StatusRevisao,
    SugestaoNormalizacao,
    Usuario,
)
from app.workers.tasks import normalizar_produtos_pendentes

router = APIRouter()


@router.post("/normalizar")
async def disparar_normalizacao(
    cliente_caso_id: int = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Dispara, de forma assíncrona, a normalização por IA de todos os itens
    pendentes (sem produto_canonico e sem sugestão já criada) de um caso.
    """
    task = normalizar_produtos_pendentes.delay(cliente_caso_id)
    return {"status": "processando", "task_id": task.id}


@router.get("/normalizar/{task_id}/status")
async def status_normalizacao(task_id: str, usuario: Usuario = Depends(usuario_atual_ativo)):
    from app.workers.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "resultado": result.result if result.ready() else None}


@router.get("/canonicos")
async def listar_canonicos(
    cliente_caso_id: int,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """Lista os produtos canônicos de um caso, para popular o filtro "Categoria" da tela."""
    db: Session = SessionLocal()
    try:
        canonicos = (
            db.query(ProdutoCanonico)
            .filter(ProdutoCanonico.cliente_caso_id == cliente_caso_id)
            .order_by(ProdutoCanonico.nome_canonico)
            .all()
        )
        return [
            {"id": c.id, "nome_canonico": c.nome_canonico, "categoria": c.categoria}
            for c in canonicos
        ]
    finally:
        db.close()


@router.post("/canonicos")
async def criar_canonico(
    cliente_caso_id: int = Body(..., embed=True),
    nome_canonico: str = Body(..., embed=True),
    categoria: str | None = Body(None, embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Cria manualmente um produto canônico (fora do fluxo de sugestão da IA) --
    usado, por exemplo, quando o revisor escolhe "+ Criar novo" ao corrigir
    uma sugestão. Checa duplicidade antes de inserir para devolver 400 em vez
    de deixar estourar a UniqueConstraint uq_produto_canonico_caso_nome.
    """
    db: Session = SessionLocal()
    try:
        existente = (
            db.query(ProdutoCanonico)
            .filter(
                ProdutoCanonico.cliente_caso_id == cliente_caso_id,
                ProdutoCanonico.nome_canonico == nome_canonico,
            )
            .first()
        )
        if existente is not None:
            raise HTTPException(
                status_code=400,
                detail=f"já existe um produto canônico '{nome_canonico}' para o caso {cliente_caso_id}",
            )

        canonico = ProdutoCanonico(
            cliente_caso_id=cliente_caso_id, nome_canonico=nome_canonico, categoria=categoria
        )
        db.add(canonico)
        db.flush()  # popula canonico.id antes do log e do retorno, sem commitar ainda

        db.add(
            LogAuditoria(
                usuario_id=usuario.id,
                acao="criacao_produto_canonico",
                resultado_resumo=(
                    f"Produto canônico {canonico.id} criado: nome '{nome_canonico}', "
                    f"categoria '{categoria}', caso {cliente_caso_id}"
                ),
            )
        )
        db.commit()
        return {"id": canonico.id, "nome_canonico": canonico.nome_canonico, "categoria": canonico.categoria}
    finally:
        db.close()


@router.patch("/canonicos/{produto_canonico_id}")
async def editar_canonico(
    produto_canonico_id: int,
    nome_canonico: str | None = Body(None, embed=True),
    categoria: str | None = Body(None, embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Edita nome e/ou categoria de um produto canônico existente, com log de
    auditoria. `categoria=""` limpa o campo (vira NULL) -- diferente de
    categoria omitido/None, que significa "não mexer nesse campo".
    """
    if nome_canonico is None and categoria is None:
        raise HTTPException(status_code=400, detail="informe nome_canonico e/ou categoria")

    db: Session = SessionLocal()
    try:
        canonico = db.get(ProdutoCanonico, produto_canonico_id)
        if canonico is None:
            raise HTTPException(status_code=404, detail="produto canônico não encontrado")

        nome_antigo = canonico.nome_canonico
        categoria_antiga = canonico.categoria
        mudancas = []

        if nome_canonico is not None and nome_canonico != nome_antigo:
            conflito = (
                db.query(ProdutoCanonico)
                .filter(
                    ProdutoCanonico.cliente_caso_id == canonico.cliente_caso_id,
                    ProdutoCanonico.nome_canonico == nome_canonico,
                    ProdutoCanonico.id != produto_canonico_id,
                )
                .first()
            )
            if conflito is not None:
                raise HTTPException(
                    status_code=400,
                    detail=f"já existe um produto canônico '{nome_canonico}' para este caso",
                )
            mudancas.append(f"nome '{nome_antigo}'->'{nome_canonico}'")
            canonico.nome_canonico = nome_canonico

        if categoria is not None:
            categoria_nova = None if categoria == "" else categoria
            if categoria_nova != categoria_antiga:
                mudancas.append(f"categoria '{categoria_antiga}'->'{categoria_nova}'")
                canonico.categoria = categoria_nova

        if mudancas:
            db.add(
                LogAuditoria(
                    usuario_id=usuario.id,
                    acao="edicao_produto_canonico",
                    resultado_resumo=(
                        f"Produto canônico {produto_canonico_id} editado: " + ", ".join(mudancas)
                    ),
                )
            )

        db.commit()
        return {"id": canonico.id, "nome_canonico": canonico.nome_canonico, "categoria": canonico.categoria}
    finally:
        db.close()


@router.get("/sugestoes")
async def listar_sugestoes(
    cliente_caso_id: int,
    status: str = "pendente",
    categoria: str | None = None,
    fornecedor: str | None = None,
    busca: str | None = None,
    limit: int = 50,
    offset: int = 0,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Lista sugestões de normalização (join com o item, a nota e o canônico
    sugerido) de um caso, para revisão humana. `status="todos"` remove o
    filtro por status; qualquer outro valor precisa bater com StatusRevisao.
    """
    db: Session = SessionLocal()
    try:
        query = (
            db.query(SugestaoNormalizacao, ItemNota, Nota, ProdutoCanonico)
            .join(ItemNota, ItemNota.id == SugestaoNormalizacao.item_nota_id)
            .join(Nota, Nota.id == ItemNota.nota_id)
            .join(
                ProdutoCanonico,
                ProdutoCanonico.id == SugestaoNormalizacao.produto_canonico_sugerido_id,
            )
            .filter(Nota.cliente_caso_id == cliente_caso_id)
        )

        if status != "todos":
            try:
                status_enum = StatusRevisao(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Status inválido: {status}")
            query = query.filter(SugestaoNormalizacao.status == status_enum)

        if categoria is not None:
            query = query.filter(ProdutoCanonico.categoria == categoria)
        if fornecedor is not None:
            query = query.filter(Nota.emitente_nome == fornecedor)
        if busca is not None:
            termo = f"%{busca}%"
            query = query.filter(
                or_(
                    ItemNota.descricao_original.ilike(termo),
                    ProdutoCanonico.nome_canonico.ilike(termo),
                )
            )

        total = query.count()
        resultados = (
            query.order_by(SugestaoNormalizacao.criado_em.desc(), SugestaoNormalizacao.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        itens = [
            {
                "id": sugestao.id,
                "item_nota_id": item.id,
                "descricao_original": item.descricao_original,
                "produto_canonico_sugerido_id": sugestao.produto_canonico_sugerido_id,
                "nome_canonico": canonico.nome_canonico,
                "categoria": canonico.categoria,
                "fornecedor": nota.emitente_nome,
                "confianca": float(sugestao.confianca),
                "status": sugestao.status.value,
                "criado_em": sugestao.criado_em,
            }
            for sugestao, item, nota, canonico in resultados
        ]
        return {"itens": itens, "total": total}
    finally:
        db.close()


def _revisar(
    db: Session,
    sugestao_id: int,
    usuario_id: int,
    confirmado: bool,
    produto_canonico_override_id: int | None = None,
) -> dict:
    """
    Fluxo compartilhado por confirmar/rejeitar, unitário ou em lote: marca o
    status da sugestão, grava quem/quando revisou, propaga
    produto_canonico_id ao item quando confirmado, e registra o LogAuditoria
    correspondente. Não commita -- quem chama decide o momento (uma sugestão
    por vez ou um lote inteiro em uma única transação).

    `produto_canonico_override_id`: usado só pelo fluxo de "corrigir"
    (escolher outro canônico que não o sugerido pela IA). Quando presente,
    exige que a sugestão ainda esteja PENDENTE (corrigir só faz sentido
    antes de uma decisão já tomada) e NÃO altera
    produto_canonico_sugerido_id -- só o produto_canonico_id do item, para
    preservar o que a IA sugeriu originalmente.
    """
    sugestao = db.get(SugestaoNormalizacao, sugestao_id)
    if sugestao is None:
        return {"status": "erro", "motivo": "sugestão não encontrada"}

    if produto_canonico_override_id is not None and sugestao.status != StatusRevisao.PENDENTE:
        return {"status": "erro", "motivo": "sugestão não está pendente"}

    sugestao.status = StatusRevisao.CONFIRMADO if confirmado else StatusRevisao.REJEITADO
    sugestao.revisado_por_usuario_id = usuario_id
    sugestao.revisado_em = datetime.utcnow()

    item = db.get(ItemNota, sugestao.item_nota_id)

    if confirmado:
        produto_id = (
            produto_canonico_override_id
            if produto_canonico_override_id is not None
            else sugestao.produto_canonico_sugerido_id
        )
        item.produto_canonico_id = produto_id
        if produto_canonico_override_id is not None:
            acao = "correcao_sugestao_normalizacao"
            resumo = (
                f"Sugestão {sugestao_id} corrigida: IA sugeriu produto canônico "
                f"{sugestao.produto_canonico_sugerido_id}, usuário escolheu {produto_id}"
            )
        else:
            acao = "confirmacao_sugestao_normalizacao"
            resumo = (
                f"Sugestão {sugestao_id} confirmada: item '{item.descricao_original}' "
                f"-> produto canônico {item.produto_canonico_id}"
            )
    else:
        acao = "rejeicao_sugestao_normalizacao"
        resumo = f"Sugestão {sugestao_id} rejeitada"

    db.add(LogAuditoria(usuario_id=usuario_id, acao=acao, resultado_resumo=resumo))

    return {"status": "ok", "sugestao_id": sugestao_id}


@router.post("/sugestoes/lote/confirmar")
async def confirmar_sugestoes_lote(
    ids: list[int] = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultados = [_revisar(db, sugestao_id, usuario.id, confirmado=True) for sugestao_id in ids]
        db.commit()
        return {"resultados": resultados}
    finally:
        db.close()


@router.post("/sugestoes/lote/rejeitar")
async def rejeitar_sugestoes_lote(
    ids: list[int] = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultados = [_revisar(db, sugestao_id, usuario.id, confirmado=False) for sugestao_id in ids]
        db.commit()
        return {"resultados": resultados}
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/confirmar")
async def confirmar_sugestao(
    sugestao_id: int,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultado = _revisar(db, sugestao_id, usuario.id, confirmado=True)
        db.commit()
        return resultado
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/rejeitar")
async def rejeitar_sugestao(
    sugestao_id: int,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        resultado = _revisar(db, sugestao_id, usuario.id, confirmado=False)
        db.commit()
        return resultado
    finally:
        db.close()


@router.post("/sugestoes/{sugestao_id}/corrigir")
async def corrigir_sugestao(
    sugestao_id: int,
    produto_canonico_id: int = Body(..., embed=True),
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Escolhe, para uma sugestão pendente, um produto canônico diferente do
    sugerido pela IA (existente ou recém-criado via POST /canonicos). O
    produto_canonico_sugerido_id da sugestão não muda -- só o
    produto_canonico_id do item passa a apontar para a escolha do usuário.
    """
    db: Session = SessionLocal()
    try:
        sugestao = db.get(SugestaoNormalizacao, sugestao_id)
        if sugestao is None:
            return {"status": "erro", "motivo": "sugestão não encontrada"}

        item = db.get(ItemNota, sugestao.item_nota_id)
        nota = db.get(Nota, item.nota_id)

        canonico_escolhido = db.get(ProdutoCanonico, produto_canonico_id)
        if canonico_escolhido is None or canonico_escolhido.cliente_caso_id != nota.cliente_caso_id:
            raise HTTPException(
                status_code=400,
                detail="produto_canonico_id inválido para o caso deste item",
            )

        resultado = _revisar(
            db,
            sugestao_id,
            usuario.id,
            confirmado=True,
            produto_canonico_override_id=produto_canonico_id,
        )
        db.commit()
        return resultado
    finally:
        db.close()
