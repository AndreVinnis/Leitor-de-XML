import html
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.auth import auth_backend, fastapi_users
from app.core.database import SessionLocal
from app.core.tokens import TokenExpirado, TokenInvalido, verificar_token_aprovacao
from app.models.models import LogAuditoria, StatusCadastro, Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioRead
from app.workers.tasks import enviar_notificacao_resultado_cadastro

router = APIRouter()

router.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/jwt")
router.include_router(fastapi_users.get_register_router(UsuarioRead, UsuarioCreate))


def _pagina(titulo: str, mensagem: str) -> HTMLResponse:
    return HTMLResponse(
        f"<html><body><h1>{html.escape(titulo)}</h1><p>{html.escape(mensagem)}</p></body></html>"
    )


@router.get("/aprovar-cadastro")
def aprovar_cadastro(token: str) -> HTMLResponse:
    return _processar_decisao(token, "aprovar")


@router.get("/reprovar-cadastro")
def reprovar_cadastro(token: str) -> HTMLResponse:
    return _processar_decisao(token, "reprovar")


def _processar_decisao(token: str, acao_esperada: str) -> HTMLResponse:
    try:
        payload = verificar_token_aprovacao(token)
    except TokenExpirado:
        return _pagina(
            "Link expirado",
            "Este link de aprovação expirou. Peça para o cadastro ser reenviado "
            "ou avise o responsável pelo sistema.",
        )
    except TokenInvalido:
        return _pagina("Link inválido", "Este link de aprovação não é válido.")

    if payload.get("acao") != acao_esperada:
        return _pagina("Link inválido", "Este link não corresponde a essa ação.")

    admin_id = payload["admin_id"]
    usuario_id = payload["usuario_id"]

    db = SessionLocal()
    try:
        admin = db.get(Usuario, admin_id)
        usuario = db.get(Usuario, usuario_id)
        if admin is None or usuario is None:
            return _pagina("Erro", "Usuário não encontrado.")

        if usuario.status_cadastro != StatusCadastro.PENDENTE:
            return _pagina(
                "Já processado",
                f"Este cadastro já havia sido {usuario.status_cadastro.value} anteriormente.",
            )

        aprovado = acao_esperada == "aprovar"
        usuario.status_cadastro = StatusCadastro.APROVADO if aprovado else StatusCadastro.REPROVADO
        usuario.is_active = aprovado
        usuario.aprovado_por_usuario_id = admin.id
        usuario.aprovado_em = datetime.utcnow()

        db.add(
            LogAuditoria(
                usuario_id=admin.id,
                acao="aprovacao_cadastro" if aprovado else "reprovacao_cadastro",
                resultado_resumo=f"Cadastro de {usuario.email} {'aprovado' if aprovado else 'reprovado'}",
            )
        )
        db.commit()

        enviar_notificacao_resultado_cadastro.delay(usuario.id, aprovado)

        return _pagina(
            "Cadastro aprovado" if aprovado else "Cadastro reprovado",
            f"O cadastro de {usuario.nome} ({usuario.email}) foi "
            f"{'aprovado' if aprovado else 'reprovado'} com sucesso.",
        )
    finally:
        db.close()
