from datetime import datetime
from enum import Enum

from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TipoNota(str, Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class Nota(Base):
    """Uma NF-e (cabeçalho). 1 XML = 1 registro aqui."""

    __tablename__ = "notas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Chave de acesso: identificador único e verificável na SEFAZ (44 dígitos)
    chave_acesso = Column(String(44), unique=True, nullable=False, index=True)
    tipo = Column(SAEnum(TipoNota), nullable=False, index=True)
    numero = Column(String(20), nullable=True)
    serie = Column(String(10), nullable=True)
    data_emissao = Column(DateTime, nullable=True)
    emitente_cnpj = Column(String(14), nullable=True, index=True)
    emitente_nome = Column(String(255), nullable=True)
    destinatario_cnpj = Column(String(14), nullable=True, index=True)
    destinatario_nome = Column(String(255), nullable=True)
    valor_total = Column(Numeric(14, 2), nullable=True)
    cliente_caso_id = Column(Integer, ForeignKey("clientes_casos.id"), nullable=True, index=True)
    arquivo_origem = Column(String(500), nullable=True)  # nome do XML original
    criado_em = Column(DateTime, default=datetime.utcnow)

    itens = relationship("ItemNota", back_populates="nota", cascade="all, delete-orphan")


class ItemNota(Base):
    """Cada <det> dentro da NF-e (um produto/linha)."""

    __tablename__ = "itens_nota"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nota_id = Column(Integer, ForeignKey("notas.id"), nullable=False, index=True)
    numero_item = Column(Integer, nullable=True)  # atributo nItem do <det>
    codigo_produto = Column(String(60), nullable=True)  # cProd
    descricao_original = Column(String(500), nullable=False)  # xProd
    ncm = Column(String(8), nullable=True, index=True)
    cfop = Column(String(4), nullable=True, index=True)
    unidade = Column(String(10), nullable=True)
    quantidade = Column(Numeric(14, 4), nullable=True)
    valor_unitario = Column(Numeric(14, 4), nullable=True)
    valor_total = Column(Numeric(14, 2), nullable=True)

    produto_canonico_id = Column(
        Integer, ForeignKey("produtos_canonicos.id"), nullable=True, index=True
    )

    nota = relationship("Nota", back_populates="itens")
    produto_canonico = relationship("ProdutoCanonico", back_populates="itens")


class ProdutoCanonico(Base):
    """
    Produto 'normalizado'. Várias descrições diferentes de itens (xProd)
    apontam para o mesmo produto_canonico após normalização por IA +
    revisão humana.

    Escopado por cliente_caso_id: cada caso tem seu próprio catálogo de
    canônicos, para não misturar vocabulário/dados de produto entre clientes
    distintos (ver AchadoReconciliacao, que já assume esse mesmo escopo).
    """

    __tablename__ = "produtos_canonicos"
    __table_args__ = (
        UniqueConstraint("cliente_caso_id", "nome_canonico", name="uq_produto_canonico_caso_nome"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_caso_id = Column(Integer, ForeignKey("clientes_casos.id"), nullable=False, index=True)
    nome_canonico = Column(String(255), nullable=False, index=True)
    categoria = Column(String(120), nullable=True, index=True)
    # Embeddings: decisão em aberto (JSON aqui é um placeholder simples;
    # ver observação do projeto sobre MySQL x pgvector x banco vetorial dedicado)
    embedding = Column(JSON, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    cliente_caso = relationship("ClienteCaso")
    itens = relationship("ItemNota", back_populates="produto_canonico")


class StatusRevisao(str, Enum):
    PENDENTE = "pendente"
    CONFIRMADO = "confirmado"
    REJEITADO = "rejeitado"


class SugestaoNormalizacao(Base):
    """
    Sugestão da IA de que um item pertence a um produto_canonico,
    aguardando (ou já com) revisão humana obrigatória.
    """

    __tablename__ = "sugestoes_normalizacao"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_nota_id = Column(Integer, ForeignKey("itens_nota.id"), nullable=False, index=True)
    produto_canonico_sugerido_id = Column(
        Integer, ForeignKey("produtos_canonicos.id"), nullable=False
    )
    confianca = Column(Numeric(5, 4), nullable=False)  # 0.0000 a 1.0000
    status = Column(SAEnum(StatusRevisao), default=StatusRevisao.PENDENTE, index=True)
    revisado_por_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    revisado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class TipoAchado(str, Enum):
    VENDA_SEM_ESTOQUE = "venda_sem_estoque"
    PRODUTO_SEM_ENTRADA = "produto_sem_entrada"
    DIVERGENCIA_NOME = "divergencia_nome"
    SALDO_NEGATIVO = "saldo_negativo"
    OUTRO = "outro"


class AchadoReconciliacao(Base):
    """
    Resultado do motor de reconciliação (lógica determinística).
    A IA nunca escreve aqui diretamente -- apenas lê e explica em texto.
    """

    __tablename__ = "achados_reconciliacao"

    id = Column(Integer, primary_key=True, autoincrement=True)
    produto_canonico_id = Column(Integer, ForeignKey("produtos_canonicos.id"), nullable=False, index=True)
    cliente_caso_id = Column(Integer, ForeignKey("clientes_casos.id"), nullable=False, index=True)
    tipo = Column(SAEnum(TipoAchado), nullable=False, index=True)
    quantidade_entrada = Column(Numeric(14, 4), default=0)
    quantidade_saida = Column(Numeric(14, 4), default=0)
    saldo = Column(Numeric(14, 4), default=0)
    periodo_inicio = Column(DateTime, nullable=True)
    periodo_fim = Column(DateTime, nullable=True)
    detalhes = Column(Text, nullable=True)  # JSON serializado com notas/itens envolvidos
    criado_em = Column(DateTime, default=datetime.utcnow)


class ClienteCaso(Base):
    """Cliente do escritório / caso jurídico, para controle de acesso."""

    __tablename__ = "clientes_casos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome_cliente = Column(String(255), nullable=False)
    identificacao_caso = Column(String(120), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class RoleUsuario(str, Enum):
    COMUM = "comum"
    ADMINISTRADOR = "administrador"


class StatusCadastro(str, Enum):
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REPROVADO = "reprovado"


class Usuario(SQLAlchemyBaseUserTable[int], Base):
    """
    Advogado/usuário do sistema. Autenticação via fastapi-users -- os
    campos email, hashed_password, is_active, is_superuser e is_verified
    vêm de SQLAlchemyBaseUserTable.

    `is_active` funciona como o "aprovado para logar": nasce False no
    registro e só vira True quando um administrador aprova o cadastro
    (ver app/core/auth.py e app/api/routes_auth.py).
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(255), nullable=False)
    role = Column(SAEnum(RoleUsuario), nullable=False, default=RoleUsuario.COMUM, index=True)
    status_cadastro = Column(
        SAEnum(StatusCadastro), nullable=False, default=StatusCadastro.PENDENTE, index=True
    )
    aprovado_por_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    aprovado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)


class LogAuditoria(Base):
    """
    Log obrigatório: quem consultou o quê, quando, e (para consultas de IA)
    a pergunta em linguagem natural + SQL gerado + resultado.
    """

    __tablename__ = "logs_auditoria"

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    acao = Column(String(120), nullable=False)  # ex: "consulta_ia", "upload_xml", "login"
    pergunta_usuario = Column(Text, nullable=True)
    sql_gerado = Column(Text, nullable=True)
    resultado_resumo = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow, index=True)
