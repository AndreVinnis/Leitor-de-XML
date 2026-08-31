from app.core.database import SessionLocal
from app.models.models import ItemNota, Nota, TipoNota
from app.parsers.nfe_parser import NFeParseError, classificar_tipo, parse_nfe_xml
from app.workers.celery_app import celery_app


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
