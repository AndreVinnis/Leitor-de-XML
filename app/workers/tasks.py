from app.ai.normalizador_produtos import sugerir_normalizacao
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.email import enviar_email
from app.core.tokens import gerar_token_aprovacao
from app.models.models import (
    ItemNota,
    Nota,
    ProdutoCanonico,
    RoleUsuario,
    StatusCadastro,
    StatusRevisao,
    SugestaoNormalizacao,
    TipoNota,
    Usuario,
)
from app.parsers.nfe_parser import NFeParseError, classificar_tipo, parse_nfe_xml
from app.workers.celery_app import celery_app

TAMANHO_LOTE_IA = 50


@celery_app.task(name="processar_xml_nfe")
def processar_xml_nfe(caminho_arquivo: str, cnpj_cliente: str, cliente_caso_id: int) -> dict:
    """
    Processa um único arquivo XML de NF-e:
    1. Faz parsing determinístico (sem IA).
    2. Classifica como entrada/saída com base no CNPJ do cliente do caso.
    3. Persiste nota + itens no banco (sem normalização de produto ainda --
       isso acontece em uma etapa posterior, assíncrona também).
    """
    db = SessionLocal()
    try:
        nota_dto = parse_nfe_xml(caminho_arquivo)
        tipo = classificar_tipo(nota_dto, cnpj_cliente)

        existente = db.query(Nota).filter_by(chave_acesso=nota_dto.chave_acesso).first()
        if existente:
            return {"status": "ja_existente", "chave_acesso": nota_dto.chave_acesso}

        nota = Nota(
            chave_acesso=nota_dto.chave_acesso,
            tipo=TipoNota(tipo),
            numero=nota_dto.numero,
            serie=nota_dto.serie,
            data_emissao=nota_dto.data_emissao,
            emitente_cnpj=nota_dto.emitente_cnpj,
            emitente_nome=nota_dto.emitente_nome,
            destinatario_cnpj=nota_dto.destinatario_cnpj,
            destinatario_nome=nota_dto.destinatario_nome,
            valor_total=nota_dto.valor_total,
            cliente_caso_id=cliente_caso_id,
            arquivo_origem=caminho_arquivo,
        )
        db.add(nota)
        db.flush()  # garante nota.id antes de criar os itens

        for item_dto in nota_dto.itens:
            db.add(
                ItemNota(
                    nota_id=nota.id,
                    numero_item=item_dto.numero_item,
                    codigo_produto=item_dto.codigo_produto,
                    descricao_original=item_dto.descricao_original,
                    ncm=item_dto.ncm,
                    cfop=item_dto.cfop,
                    unidade=item_dto.unidade,
                    quantidade=item_dto.quantidade,
                    valor_unitario=item_dto.valor_unitario,
                    valor_total=item_dto.valor_total,
                )
            )

        db.commit()
        return {"status": "ok", "chave_acesso": nota_dto.chave_acesso, "itens": len(nota_dto.itens)}

    except NFeParseError as exc:
        db.rollback()
        return {"status": "erro", "arquivo": caminho_arquivo, "motivo": str(exc)}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"status": "erro_inesperado", "arquivo": caminho_arquivo, "motivo": str(exc)}
    finally:
        db.close()


@celery_app.task(name="enviar_notificacao_novo_cadastro")
def enviar_notificacao_novo_cadastro(usuario_id: int) -> dict:
    """
    Avisa todos os administradores já aprovados sobre um novo cadastro
    pendente, com links individuais de aprovação/reprovação (token assinado,
    de uso único e que expira em settings.token_aprovacao_expira_minutos).
    """
    db = SessionLocal()
    try:
        usuario = db.get(Usuario, usuario_id)
        if usuario is None:
            return {"status": "erro", "motivo": "usuário não encontrado"}

        admins = (
            db.query(Usuario)
            .filter(Usuario.role == RoleUsuario.ADMINISTRADOR)
            .filter(Usuario.status_cadastro == StatusCadastro.APROVADO)
            .all()
        )

        for admin in admins:
            token_aprovar = gerar_token_aprovacao(admin.id, usuario.id, "aprovar")
            token_reprovar = gerar_token_aprovacao(admin.id, usuario.id, "reprovar")
            link_aprovar = f"{settings.api_base_url}/api/auth/aprovar-cadastro?token={token_aprovar}"
            link_reprovar = f"{settings.api_base_url}/api/auth/reprovar-cadastro?token={token_reprovar}"

            corpo = (
                "Novo cadastro aguardando aprovação:\n\n"
                f"Nome: {usuario.nome}\n"
                f"E-mail: {usuario.email}\n\n"
                f"Aprovar: {link_aprovar}\n"
                f"Reprovar: {link_reprovar}\n\n"
                f"Este link expira em {settings.token_aprovacao_expira_minutos} minutos."
            )
            enviar_email(admin.email, "Novo cadastro aguardando aprovação", corpo)

        return {"status": "ok", "admins_notificados": len(admins)}
    finally:
        db.close()


@celery_app.task(name="enviar_notificacao_resultado_cadastro")
def enviar_notificacao_resultado_cadastro(usuario_id: int, aprovado: bool) -> dict:
    """Avisa o próprio usuário se o cadastro dele foi aprovado ou reprovado."""
    db = SessionLocal()
    try:
        usuario = db.get(Usuario, usuario_id)
        if usuario is None:
            return {"status": "erro", "motivo": "usuário não encontrado"}

        if aprovado:
            assunto = "Seu cadastro foi aprovado"
            corpo = (
                f"Olá, {usuario.nome}.\n\n"
                "Seu cadastro no sistema foi aprovado por um administrador. "
                "Você já pode fazer login normalmente."
            )
        else:
            assunto = "Seu cadastro não foi aprovado"
            corpo = (
                f"Olá, {usuario.nome}.\n\n"
                "Seu cadastro no sistema não foi aprovado por um administrador. "
                "Se acredita que isso é um engano, entre em contato com o "
                "responsável pelo sistema."
            )

        enviar_email(usuario.email, assunto, corpo)
        return {"status": "ok"}
    finally:
        db.close()


def _normalizar_chave(descricao: str) -> str:
    return descricao.strip().upper()


@celery_app.task(name="normalizar_produtos_pendentes")
def normalizar_produtos_pendentes(cliente_caso_id: int | None = None) -> dict:
    """
    Busca itens de nota sem produto_canonico e sem sugestão pendente/já
    revisada, deduplica pela descrição original e pede à IA para sugerir
    um produto canônico (existente ou novo) para cada descrição distinta.
    Cria as SugestaoNormalizacao com status=PENDENTE para revisão humana --
    a IA nunca grava produto_canonico_id diretamente em itens_nota.
    """
    db = SessionLocal()
    try:
        query = (
            db.query(ItemNota)
            .outerjoin(SugestaoNormalizacao, SugestaoNormalizacao.item_nota_id == ItemNota.id)
            .filter(ItemNota.produto_canonico_id.is_(None))
            .filter(SugestaoNormalizacao.id.is_(None))
        )
        if cliente_caso_id is not None:
            query = query.join(Nota, Nota.id == ItemNota.nota_id).filter(
                Nota.cliente_caso_id == cliente_caso_id
            )

        itens_pendentes = query.all()
        if not itens_pendentes:
            return {"status": "ok", "descricoes_unicas": 0, "sugestoes_criadas": 0}

        # Deduplica por descrição normalizada -- poucas descrições distintas,
        # muitas notas repetindo a mesma descrição.
        grupos: dict[str, list[ItemNota]] = {}
        descricao_original_por_chave: dict[str, str] = {}
        for item in itens_pendentes:
            chave = _normalizar_chave(item.descricao_original)
            grupos.setdefault(chave, []).append(item)
            descricao_original_por_chave.setdefault(chave, item.descricao_original)

        canonicos_existentes = [
            {"id": c.id, "nome_canonico": c.nome_canonico, "categoria": c.categoria}
            for c in db.query(ProdutoCanonico).all()
        ]
        ids_canonicos_existentes = {c["id"] for c in canonicos_existentes}

        chaves = list(grupos.keys())
        sugestoes_criadas = 0
        produtos_canonicos_criados = 0

        for i in range(0, len(chaves), TAMANHO_LOTE_IA):
            lote_chaves = chaves[i : i + TAMANHO_LOTE_IA]
            descricoes_lote = [descricao_original_por_chave[c] for c in lote_chaves]

            resultados = sugerir_normalizacao(descricoes_lote, canonicos_existentes)

            resultados_por_chave = {
                _normalizar_chave(r.descricao_original): r for r in resultados
            }

            for chave in lote_chaves:
                resultado = resultados_por_chave.get(chave)
                if resultado is None:
                    continue  # IA não retornou sugestão para essa descrição

                produto_canonico_id = resultado.produto_canonico_id
                if produto_canonico_id is not None and produto_canonico_id not in ids_canonicos_existentes:
                    produto_canonico_id = None  # segurança: IA apontou id inexistente

                if produto_canonico_id is None:
                    if resultado.novo_produto_canonico is None:
                        continue  # sem correspondência e sem produto novo -- ignora
                    novo = ProdutoCanonico(
                        nome_canonico=resultado.novo_produto_canonico.nome_canonico,
                        categoria=resultado.novo_produto_canonico.categoria,
                    )
                    db.add(novo)
                    db.flush()  # garante novo.id
                    produto_canonico_id = novo.id
                    ids_canonicos_existentes.add(produto_canonico_id)
                    produtos_canonicos_criados += 1

                for item in grupos[chave]:
                    db.add(
                        SugestaoNormalizacao(
                            item_nota_id=item.id,
                            produto_canonico_sugerido_id=produto_canonico_id,
                            confianca=resultado.confianca,
                            status=StatusRevisao.PENDENTE,
                        )
                    )
                    sugestoes_criadas += 1

        db.commit()
        return {
            "status": "ok",
            "descricoes_unicas": len(chaves),
            "itens_pendentes": len(itens_pendentes),
            "produtos_canonicos_criados": produtos_canonicos_criados,
            "sugestoes_criadas": sugestoes_criadas,
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"status": "erro_inesperado", "motivo": str(exc)}
    finally:
        db.close()
