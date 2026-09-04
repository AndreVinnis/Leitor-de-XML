from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import ClienteCaso, Usuario
from app.schemas.caso import ClienteCasoCreate, ClienteCasoRead

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
