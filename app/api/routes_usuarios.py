from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.routes_auth import efetivar_decisao_cadastro
from app.core.auth import requer_administrador
from app.core.database import SessionLocal
from app.models.models import LogAuditoria, RoleUsuario, StatusCadastro, Usuario

router = APIRouter()


def _serializar(usuario: Usuario) -> dict:
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "role": usuario.role.value,
        "status_cadastro": usuario.status_cadastro.value,
        "is_active": usuario.is_active,
        "criado_em": usuario.criado_em,
    }


@router.get("")
async def listar_usuarios(
    role: str | None = None,
    status_cadastro: str | None = None,
    busca: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: Usuario = Depends(requer_administrador),
):
    """
    Lista os usuários do sistema (não escopado por caso -- RBAC é global, ver
    decisão de 2026-09-05 na documentação do projeto). Alimenta tanto a aba
    "Usuários" de Configurações (filtro por papel/status/busca) quanto a tela
    de Aprovação de Cadastros (filtro por status_cadastro apenas).
    """
    db: Session = SessionLocal()
    try:
        query = db.query(Usuario)

        if role is not None:
            try:
                role_enum = RoleUsuario(role)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Papel inválido: {role}")
            query = query.filter(Usuario.role == role_enum)

        if status_cadastro is not None and status_cadastro != "todos":
            try:
                status_enum = StatusCadastro(status_cadastro)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Status inválido: {status_cadastro}")
            query = query.filter(Usuario.status_cadastro == status_enum)

        if busca is not None:
            termo = f"%{busca}%"
            query = query.filter(or_(Usuario.nome.ilike(termo), Usuario.email.ilike(termo)))

        total = query.count()
        resultados = query.order_by(Usuario.criado_em.desc()).offset(offset).limit(limit).all()
        return {"itens": [_serializar(u) for u in resultados], "total": total}
    finally:
        db.close()


@router.patch("/{usuario_id}")
async def editar_usuario(
    usuario_id: int,
    role: str | None = Body(None, embed=True),
    is_active: bool | None = Body(None, embed=True),
    admin: Usuario = Depends(requer_administrador),
):
    """
    Altera papel de acesso e/ou ativa-desativa um usuário. Um admin não pode
    usar esta rota sobre a própria conta (evita autobloqueio: rebaixar o
    próprio papel ou se desativar sem ter outro admin para reverter).
    """
    if role is None and is_active is None:
        raise HTTPException(status_code=400, detail="informe role e/ou is_active")

    if usuario_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="não é possível alterar o próprio papel ou status por aqui",
        )

    db: Session = SessionLocal()
    try:
        usuario_alvo = db.get(Usuario, usuario_id)
        if usuario_alvo is None:
            raise HTTPException(status_code=404, detail="usuário não encontrado")

        mudancas = []

        if role is not None:
            try:
                role_enum = RoleUsuario(role)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Papel inválido: {role}")
            if role_enum != usuario_alvo.role:
                mudancas.append(f"papel '{usuario_alvo.role.value}'->'{role_enum.value}'")
                usuario_alvo.role = role_enum

        if is_active is not None and is_active != usuario_alvo.is_active:
            mudancas.append(f"is_active {usuario_alvo.is_active}->{is_active}")
            usuario_alvo.is_active = is_active

        if mudancas:
            db.add(
                LogAuditoria(
                    usuario_id=admin.id,
                    acao="edicao_usuario",
                    resultado_resumo=f"Usuário {usuario_id} editado: " + ", ".join(mudancas),
                )
            )

        db.commit()
        return _serializar(usuario_alvo)
    finally:
        db.close()


def _decidir_cadastro(db: Session, usuario_id: int, admin_id: int, aprovado: bool) -> dict:
    """
    Fluxo compartilhado por aprovar/reprovar, unitário ou em lote -- mesmo
    espírito de _revisar em app/api/routes_produtos.py. Não commita.
    """
    usuario_alvo = db.get(Usuario, usuario_id)
    if usuario_alvo is None:
        return {"status": "erro", "motivo": "usuário não encontrado", "usuario_id": usuario_id}

    if usuario_alvo.status_cadastro != StatusCadastro.PENDENTE:
        return {"status": "erro", "motivo": "cadastro não está pendente", "usuario_id": usuario_id}

    efetivar_decisao_cadastro(db, usuario_alvo, admin_id, aprovado)
    return {"status": "ok", "usuario_id": usuario_id}


@router.post("/{usuario_id}/aprovar")
async def aprovar_usuario(usuario_id: int, admin: Usuario = Depends(requer_administrador)):
    db: Session = SessionLocal()
    try:
        resultado = _decidir_cadastro(db, usuario_id, admin.id, aprovado=True)
        db.commit()
        return resultado
    finally:
        db.close()


@router.post("/{usuario_id}/reprovar")
async def reprovar_usuario(usuario_id: int, admin: Usuario = Depends(requer_administrador)):
    db: Session = SessionLocal()
    try:
        resultado = _decidir_cadastro(db, usuario_id, admin.id, aprovado=False)
        db.commit()
        return resultado
    finally:
        db.close()


@router.post("/aprovar-lote")
async def aprovar_usuarios_lote(
    ids: list[int] = Body(..., embed=True),
    admin: Usuario = Depends(requer_administrador),
):
    db: Session = SessionLocal()
    try:
        resultados = [_decidir_cadastro(db, usuario_id, admin.id, aprovado=True) for usuario_id in ids]
        db.commit()
        return {"resultados": resultados}
    finally:
        db.close()


@router.post("/reprovar-lote")
async def reprovar_usuarios_lote(
    ids: list[int] = Body(..., embed=True),
    admin: Usuario = Depends(requer_administrador),
):
    db: Session = SessionLocal()
    try:
        resultados = [_decidir_cadastro(db, usuario_id, admin.id, aprovado=False) for usuario_id in ids]
        db.commit()
        return {"resultados": resultados}
    finally:
        db.close()
