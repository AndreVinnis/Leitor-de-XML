from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import requer_administrador, usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import (
    AchadoReconciliacao,
    ArquivoLote,
    ClienteCaso,
    ItemNota,
    LogAuditoria,
    Lote,
    Nota,
    ProdutoCanonico,
    SugestaoNormalizacao,
    Usuario,
)
from app.schemas.caso import ClienteCasoCreate, ClienteCasoRead, ClienteCasoUpdate

router = APIRouter()


@router.get("", response_model=list[ClienteCasoRead])
async def listar_casos(usuario: Usuario = Depends(usuario_atual_ativo)):
    """Lista os clientes/casos cadastrados -- popula o seletor de caso que
    as telas de upload/dashboard/normalização já exigem via cliente_caso_id."""
    db: Session = SessionLocal()
    try:
        return db.query(ClienteCaso).order_by(ClienteCaso.criado_em.desc()).all()
    finally:
        db.close()


@router.post("", response_model=ClienteCasoRead)
async def criar_caso(
    dados: ClienteCasoCreate,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    db: Session = SessionLocal()
    try:
        caso = ClienteCaso(
            nome_cliente=dados.nome_cliente,
            identificacao_caso=dados.identificacao_caso,
            cnpj_cliente=dados.cnpj_cliente,
        )
        db.add(caso)
        db.commit()
        db.refresh(caso)
        return caso
    finally:
        db.close()


@router.get("/{caso_id}", response_model=ClienteCasoRead)
async def obter_caso(caso_id: int, usuario: Usuario = Depends(usuario_atual_ativo)):
    db: Session = SessionLocal()
    try:
        caso = db.get(ClienteCaso, caso_id)
        if caso is None:
            raise HTTPException(status_code=404, detail="Caso não encontrado.")
        return caso
    finally:
        db.close()


@router.patch("/{caso_id}", response_model=ClienteCasoRead)
async def atualizar_caso(
    caso_id: int,
    dados: ClienteCasoUpdate,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """Edita um caso já existente -- principal uso hoje é preencher/corrigir
    o cnpj_cliente de casos criados antes desse campo existir."""
    db: Session = SessionLocal()
    try:
        caso = db.get(ClienteCaso, caso_id)
        if caso is None:
            raise HTTPException(status_code=404, detail="Caso não encontrado.")
        campos = dados.model_dump(exclude_unset=True)
        if (
            "cnpj_cliente" in campos
            and caso.cnpj_cliente is not None
            and campos["cnpj_cliente"] != caso.cnpj_cliente
        ):
            raise HTTPException(
                status_code=422, detail="O CNPJ não pode ser alterado após o cadastro."
            )
        for campo, valor in campos.items():
            setattr(caso, campo, valor)
        db.commit()
        db.refresh(caso)
        return caso
    finally:
        db.close()


@router.delete("/{caso_id}", status_code=204)
async def excluir_caso(
    caso_id: int,
    admin: Usuario = Depends(requer_administrador),
):
    """Exclui um cliente/caso e tudo que depende dele -- notas, itens,
    sugestões de normalização, produtos canônicos, achados de reconciliação
    e lotes de upload (essas duas últimas não foram pedidas explicitamente,
    mas têm FK obrigatória para clientes_casos, então precisam ser limpas
    também ou o delete do caso quebra com IntegrityError). logs_auditoria
    nunca é tocado -- não referencia cliente_caso_id."""
    db: Session = SessionLocal()
    try:
        caso = db.get(ClienteCaso, caso_id)
        if caso is None:
            raise HTTPException(status_code=404, detail="Caso não encontrado.")

        nota_ids = [
            row[0] for row in db.query(Nota.id).filter(Nota.cliente_caso_id == caso_id).all()
        ]
        produto_ids = [
            row[0]
            for row in db.query(ProdutoCanonico.id)
            .filter(ProdutoCanonico.cliente_caso_id == caso_id)
            .all()
        ]
        lote_ids = [
            row[0] for row in db.query(Lote.id).filter(Lote.cliente_caso_id == caso_id).all()
        ]
        item_ids = (
            [
                row[0]
                for row in db.query(ItemNota.id).filter(ItemNota.nota_id.in_(nota_ids)).all()
            ]
            if nota_ids
            else []
        )

        if item_ids:
            db.query(SugestaoNormalizacao).filter(
                SugestaoNormalizacao.item_nota_id.in_(item_ids)
            ).delete(synchronize_session=False)
        if produto_ids:
            db.query(SugestaoNormalizacao).filter(
                SugestaoNormalizacao.produto_canonico_sugerido_id.in_(produto_ids)
            ).delete(synchronize_session=False)

        db.query(AchadoReconciliacao).filter(
            AchadoReconciliacao.cliente_caso_id == caso_id
        ).delete(synchronize_session=False)

        if lote_ids:
            db.query(ArquivoLote).filter(ArquivoLote.lote_id.in_(lote_ids)).delete(
                synchronize_session=False
            )

        if nota_ids:
            db.query(ItemNota).filter(ItemNota.nota_id.in_(nota_ids)).delete(
                synchronize_session=False
            )

        db.query(Nota).filter(Nota.cliente_caso_id == caso_id).delete(
            synchronize_session=False
        )
        db.query(Lote).filter(Lote.cliente_caso_id == caso_id).delete(
            synchronize_session=False
        )
        db.query(ProdutoCanonico).filter(ProdutoCanonico.cliente_caso_id == caso_id).delete(
            synchronize_session=False
        )

        db.add(
            LogAuditoria(
                usuario_id=admin.id,
                acao="exclusao_cliente_caso",
                resultado_resumo=(
                    f"Cliente/caso #{caso_id} ({caso.nome_cliente}) excluído: "
                    f"{len(nota_ids)} nota(s), {len(item_ids)} item(ns), "
                    f"{len(produto_ids)} produto(s) canônico(s)."
                ),
            )
        )

        db.delete(caso)
        db.commit()
    finally:
        db.close()
    return None
