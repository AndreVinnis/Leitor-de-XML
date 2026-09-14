from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import ClienteCaso, Usuario
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
        for campo, valor in dados.model_dump(exclude_unset=True).items():
            setattr(caso, campo, valor)
        db.commit()
        db.refresh(caso)
        return caso
    finally:
        db.close()
