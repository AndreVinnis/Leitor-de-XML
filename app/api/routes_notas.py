from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.auth import usuario_atual_ativo
from app.core.database import SessionLocal
from app.models.models import ArquivoLote, Lote, Nota, StatusProcessamento, TipoNota, Usuario

router = APIRouter()


@router.get("")
async def listar_notas(
    cliente_caso_id: int | None = None,
    status: str | None = None,
    tipo: str | None = None,
    q: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limit: int = 50,
    offset: int = 0,
    usuario: Usuario = Depends(usuario_atual_ativo),
):
    """
    Alimenta o dashboard ("Notas recentes") e a tela Notas Fiscais: numero,
    tipo, emitente_nome, destinatario_nome, data_emissao, valor_total e o
    status de processamento (que vive em ArquivoLote, não em Nota -- ver
    app/models/models.py).
    """
    db: Session = SessionLocal()
    try:
        query = db.query(Nota, ArquivoLote.status).outerjoin(
            ArquivoLote, ArquivoLote.nota_id == Nota.id
        )
        if cliente_caso_id is not None:
            query = query.filter(Nota.cliente_caso_id == cliente_caso_id)
        if status is not None:
            query = query.filter(ArquivoLote.status == StatusProcessamento(status))
        if tipo is not None:
            query = query.filter(Nota.tipo == TipoNota(tipo))
        if q is not None:
            termo = f"%{q}%"
            query = query.filter(
                or_(
                    Nota.numero.ilike(termo),
                    Nota.chave_acesso.ilike(termo),
                    Nota.emitente_nome.ilike(termo),
                )
            )
        if data_inicio is not None:
            query = query.filter(Nota.data_emissao >= data_inicio)
        if data_fim is not None:
            # data_emissao é DateTime e costuma ter hora (não só a meia-noite
            # do dia); comparar com "<=" contra a date pura excluiria o
            # próprio dia final. Soma 1 dia e usa "<" para incluir o dia
            # inteiro.
            query = query.filter(Nota.data_emissao < data_fim + timedelta(days=1))

        total = query.count()
        resultados = query.order_by(Nota.criado_em.desc()).offset(offset).limit(limit).all()

        itens = [
            {
                "id": nota.id,
                "numero": nota.numero,
                "tipo": nota.tipo.value if nota.tipo is not None else None,
                "emitente_nome": nota.emitente_nome,
                "destinatario_nome": nota.destinatario_nome,
                "data_emissao": nota.data_emissao,
                # Decimal serializado como string, não float: é dinheiro e o
                # frontend não deve receber ponto flutuante nesse campo.
                "valor_total": str(nota.valor_total) if nota.valor_total is not None else None,
                "status": status_arquivo.value if status_arquivo is not None else None,
            }
            for nota, status_arquivo in resultados
        ]
        return {"itens": itens, "total": total}
    finally:
        db.close()


@router.get("/lotes/{lote_id}")
async def progresso_lote(lote_id: str, usuario: Usuario = Depends(usuario_atual_ativo)):
    """
    Progresso agregado de um lote de upload, substituindo a necessidade de
    N chamadas a GET /upload/{task_id}/status (uma por arquivo).
    """
    db: Session = SessionLocal()
    try:
        lote = db.get(Lote, lote_id)
        if lote is None:
            raise HTTPException(status_code=404, detail="Lote não encontrado.")

        arquivos = db.query(ArquivoLote).filter(ArquivoLote.lote_id == lote_id).all()
        concluidos = sum(1 for a in arquivos if a.status != StatusProcessamento.PENDENTE)
        com_erro = sum(1 for a in arquivos if a.status == StatusProcessamento.ERRO)

        return {
            "lote_id": lote_id,
            "total_arquivos": lote.total_arquivos,
            "concluidos": concluidos,
            "com_erro": com_erro,
            "arquivos": [
                {
                    "id": a.id,
                    "nome_arquivo": a.nome_arquivo,
                    "status": a.status.value if a.status is not None else None,
                    "motivo_erro": a.motivo_erro,
                    "nota_id": a.nota_id,
                }
                for a in arquivos
            ],
        }
    finally:
        db.close()


@router.get("/{nota_id}")
async def obter_nota(nota_id: int, usuario: Usuario = Depends(usuario_atual_ativo)):
    """Cabeçalho da nota (+ status e arquivo de origem, via ArquivoLote) e seus itens."""
    db: Session = SessionLocal()
    try:
        nota = db.get(Nota, nota_id)
        if nota is None:
            raise HTTPException(status_code=404, detail="Nota não encontrada.")

        arquivo_lote = (
            db.query(ArquivoLote).filter(ArquivoLote.nota_id == nota.id).one_or_none()
        )

        return {
            "id": nota.id,
            "chave_acesso": nota.chave_acesso,
            "tipo": nota.tipo.value,
            "numero": nota.numero,
            "serie": nota.serie,
            "data_emissao": nota.data_emissao,
            "emitente_cnpj": nota.emitente_cnpj,
            "emitente_nome": nota.emitente_nome,
            "destinatario_cnpj": nota.destinatario_cnpj,
            "destinatario_nome": nota.destinatario_nome,
            # Dinheiro: string decimal, nunca float -- mesma regra de listar_notas.
            "valor_total": str(nota.valor_total) if nota.valor_total is not None else None,
            "cliente_caso_id": nota.cliente_caso_id,
            "status": arquivo_lote.status.value if arquivo_lote is not None and arquivo_lote.status is not None else None,
            "arquivo_origem": arquivo_lote.nome_arquivo if arquivo_lote is not None else None,
            "itens": [
                {
                    "id": item.id,
                    "numero_item": item.numero_item,
                    "codigo_produto": item.codigo_produto,
                    "descricao_original": item.descricao_original,
                    "ncm": item.ncm,
                    "cfop": item.cfop,
                    "unidade": item.unidade,
                    "quantidade": str(item.quantidade) if item.quantidade is not None else None,
                    "valor_unitario": str(item.valor_unitario) if item.valor_unitario is not None else None,
                    "valor_total": str(item.valor_total) if item.valor_total is not None else None,
                    "produto_canonico_id": item.produto_canonico_id,
                    "produto_canonico_nome": (
                        item.produto_canonico.nome_canonico if item.produto_canonico is not None else None
                    ),
                }
                for item in nota.itens
            ],
        }
    finally:
        db.close()
