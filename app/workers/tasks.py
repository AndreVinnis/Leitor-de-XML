import time

from celery.utils.log import get_task_logger
from sqlalchemy.exc import IntegrityError

from app.ai.embeddings import gerar_embeddings, selecionar_candidatos_similares, serializar_embedding
from app.ai.normalizador_produtos import sugerir_normalizacao
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.email import enviar_email
from app.core import trava_normalizacao
from app.core.tokens import gerar_token_aprovacao
from app.models.models import (
    ArquivoLote,
    EventoNFe,
    ItemNota,
    Lote,
    Nota,
    ProdutoCanonico,
    RoleUsuario,
    SituacaoNota,
    StatusCadastro,
    StatusProcessamento,
    StatusRevisao,
    SugestaoNormalizacao,
    TipoNota,
    Usuario,
)
from app.parsers.evento_parser import TIPO_CANCELAMENTO, EventoParseError, parse_evento_xml
from app.parsers.nfe_parser import NFeParseError, classificar_tipo, parse_nfe_xml
from app.workers.celery_app import celery_app

# cStat do retEvento que contam como "o Sefaz efetivamente registrou o
# evento": 135 registrado e vinculado, 136 registrado não vinculado, 155
# cancelamento homologado fora de prazo. Um evento sem <retEvento> (só o
# pedido) ou com cStat de rejeição fica de fora -- é o que impede um pedido
# de cancelamento não homologado de cancelar a nota.
CSTAT_EVENTO_REGISTRADO = {"135", "136", "155"}

# Ambiente de produção do Sefaz -- evento de homologação (tpAmb=2) nunca
# pode alterar uma nota real, mesmo que a chave de acesso combine.
TP_AMB_PRODUCAO = "1"

logger = get_task_logger(__name__)

TAMANHO_LOTE_IA = 50

# Cada lote da normalização é enviado, salvo (commit) e só então o próximo
# segue. Um lote que falha é tentado de novo até TENTATIVAS_POR_LOTE vezes
# no total, com as esperas abaixo entre uma tentativa e outra; na última
# falha a task para e devolve o erro, mantendo os lotes anteriores já
# salvos. É a única camada de retry das chamadas ao Claude -- o normalizador
# não usa retry_anthropic, senão cada tentativa daqui viraria até 3 chamadas.
# (gerar_embeddings mantém o retry_gemini próprio, para erros transitórios
# do Gemini dentro de uma mesma tentativa.)
TENTATIVAS_POR_LOTE = 3
ESPERAS_ENTRE_TENTATIVAS = (10, 30)

# Pré-filtro por embeddings: catálogos até esse tamanho continuam indo
# inteiros no prompt (comportamento e precisão de hoje, sem custo extra de
# embedding). Acima disso, cada lote recebe só a união dos TOP_K_CANDIDATOS
# canônicos mais similares (cosseno) a cada descrição do lote, capada em
# MAX_CANDIDATOS_POR_LOTE -- ver app/ai/embeddings.py.
LIMIAR_FILTRO_EMBEDDING = 150
TOP_K_CANDIDATOS = 15
MAX_CANDIDATOS_POR_LOTE = 150


def _atualizar_status_arquivo_lote(db, arquivo_lote_id: int, resultado: dict) -> None:
    """
    Grava o desfecho terminal do processamento na linha ArquivoLote
    correspondente. Chamada a partir do `finally` de processar_xml_nfe só
    quando há de fato um resultado terminal (sucesso, duplicado ou erro sem
    mais tentativas) -- uma exceção que ainda vai ser retentada não passa por
    aqui, para não sobrescrever o PROCESSANDO com um ERRO prematuro.
    """
    arquivo_lote = db.get(ArquivoLote, arquivo_lote_id)
    if arquivo_lote is None:
        return  # não deveria acontecer, mas não é motivo para derrubar a task

    if resultado["status"] == "ok":
        arquivo_lote.status = StatusProcessamento.SUCESSO
        arquivo_lote.nota_id = resultado.get("nota_id")
    elif resultado["status"] == "ja_existente":
        arquivo_lote.status = StatusProcessamento.DUPLICADO
    elif resultado["status"] == "evento":
        # Nunca preenche nota_id aqui -- routes_notas.py busca ArquivoLote
        # por nota_id com .one_or_none() e um outerjoin que assume no máximo
        # um arquivo por nota; o rastro do arquivo de evento vive em
        # EventoNFe.arquivo_lote_id.
        arquivo_lote.status = StatusProcessamento.EVENTO
    else:  # "erro" ou "erro_inesperado"
        arquivo_lote.status = StatusProcessamento.ERRO
        arquivo_lote.motivo_erro = resultado.get("motivo")

    lote_id = arquivo_lote.lote_id
    db.commit()

    _disparar_varredura_se_lote_terminou(db, lote_id)


def _disparar_varredura_se_lote_terminou(db, lote_id: str) -> None:
    """
    Dispara aplicar_eventos_pendentes assim que o último ArquivoLote do lote
    chega a um status terminal, em vez de um countdown fixo depois do
    enfileiramento (routes_upload.py chegou a usar um countdown de 60s, mas
    o tamanho do lote não tem relação com esse número -- um lote grande pode
    não ter terminado, e um pequeno já terminou bem antes).

    A consulta roda em transação nova, aberta depois do commit acima -- vê o
    estado mais recente de todo ArquivoLote do lote, inclusive os que outros
    workers acabaram de commitar (mesma invariante de leitura cruzada usada
    em _aplicar_efeito_evento). Mais de um arquivo pode terminar "ao mesmo
    tempo" e cada um ver zero pendentes, disparando a varredura mais de uma
    vez -- inofensivo, porque aplicar_eventos_pendentes é idempotente.
    """
    pendentes = (
        db.query(ArquivoLote.id)
        .filter(
            ArquivoLote.lote_id == lote_id,
            ArquivoLote.status.in_(
                [StatusProcessamento.PENDENTE, StatusProcessamento.PROCESSANDO]
            ),
        )
        .first()
    )
    if pendentes is not None:
        return  # ainda tem arquivo do lote em andamento

    lote = db.get(Lote, lote_id)
    if lote is not None:
        aplicar_eventos_pendentes.delay(lote.cliente_caso_id)


def _marcar_processando(db, arquivo_lote_id: int) -> None:
    """
    Marca o início do processamento com commit imediato, antes de qualquer
    trabalho de fato. Separa "nunca foi processado" (PENDENTE) de "começou e
    morreu no meio" (PROCESSANDO sem nunca virar um status terminal) -- antes
    os dois casos eram indistinguíveis se o worker morresse (kill -9/OOM)
    durante o processamento, e o ArquivoLote ficava preso em PENDENTE para
    sempre.
    """
    arquivo_lote = db.get(ArquivoLote, arquivo_lote_id)
    if arquivo_lote is None:
        return
    arquivo_lote.status = StatusProcessamento.PROCESSANDO
    db.commit()


def _evento_cancela_nota(evento: EventoNFe) -> bool:
    """Política de quando um evento tem efeito jurídico sobre a nota --
    mantida separada do parser (app/parsers/evento_parser.py só extrai
    dados), no mesmo espírito de app/core/sql_seguranca.py: a leitura não
    decide, a regra decide."""
    return (
        evento.tipo_evento == TIPO_CANCELAMENTO
        and evento.cstat in CSTAT_EVENTO_REGISTRADO
        and evento.tp_amb == TP_AMB_PRODUCAO
    )


def _aplicar_efeito_evento(db, evento_id: int) -> None:
    """
    Aplica o efeito de um evento sobre a nota correspondente, se a nota já
    existir e o evento for elegível (ver _evento_cancela_nota). Idempotente:
    pode ser chamado de novo para o mesmo evento sem duplicar efeito, e sem
    reverter uma nota já cancelada.

    Só deve ser chamado a partir de uma transação aberta DEPOIS do commit do
    registro (evento ou nota) que disparou a checagem -- nunca antes. Sob
    REPEATABLE READ (default do MySQL/InnoDB), o read view nasce na primeira
    leitura da transação, não no BEGIN; ler no mesmo bloco que ainda vai
    commitar enxergaria um snapshot anterior ao commit do lado oposto
    (nota↔evento processados em paralelo por workers diferentes) e o efeito
    se perderia em silêncio. Isso está garantido hoje porque cada chamada
    ocorre logo após um db.commit() desta mesma função chamadora.
    """
    evento = db.get(EventoNFe, evento_id)
    if evento is None or evento.aplicado:
        return

    nota = (
        db.query(Nota)
        .filter(Nota.chave_acesso == evento.chave_acesso, Nota.cliente_caso_id == evento.cliente_caso_id)
        .one_or_none()
    )
    if nota is None:
        return  # órfão -- aplicado quando a nota desta chave for importada

    evento.nota_id = nota.id

    if _evento_cancela_nota(evento):
        # UPDATE condicional em vez de SELECT ... FOR UPDATE como sonda: em
        # REPEATABLE READ, FOR UPDATE numa chave que talvez não exista toma
        # gap lock e monta ciclo com o outro lado (deadlock 1213). O WHERE
        # abaixo já torna a operação um no-op se a nota já estiver cancelada.
        db.query(Nota).filter(Nota.id == nota.id, Nota.situacao != SituacaoNota.CANCELADA).update(
            {"situacao": SituacaoNota.CANCELADA, "cancelada_em": evento.data_evento}
        )

    evento.aplicado = True
    db.commit()


def _aplicar_eventos_pendentes_da_chave(db, chave_acesso: str, cliente_caso_id: int) -> None:
    """Aplica todo evento ainda não aplicado daquela chave, assim que a nota
    aparece (seja porque acabou de ser criada, seja num reprocessamento que
    caiu no ramo "já existente"). Falha aqui não pode derrubar o sucesso de
    quem chamou -- o evento continua com aplicado=False e é pego depois pela
    task aplicar_eventos_pendentes."""
    try:
        pendentes = (
            db.query(EventoNFe.id)
            .filter(
                EventoNFe.chave_acesso == chave_acesso,
                EventoNFe.cliente_caso_id == cliente_caso_id,
                EventoNFe.aplicado.is_(False),
            )
            .all()
        )
        for (evento_id,) in pendentes:
            _aplicar_efeito_evento(db, evento_id)
    except Exception:  # noqa: BLE001
        db.rollback()


def _processar_evento(db, caminho_arquivo: str, cliente_caso_id: int, arquivo_lote_id: int) -> dict:
    """Persiste um evento de NF-e e tenta aplicar o efeito imediatamente
    (a nota pode já existir). Chamado só depois que parse_nfe_xml falhou
    (ver processar_xml_nfe) -- se parse_evento_xml também falhar, quem
    decide o que reportar é o chamador, não esta função."""
    evento_dto = parse_evento_xml(caminho_arquivo)
    # Nunca NULL: MySQL/SQLite não aplicam UNIQUE entre linhas com NULL na
    # coluna, e cstat entra na chave natural do evento (ver EventoNFe).
    cstat = evento_dto.cstat or ""

    evento = EventoNFe(
        cliente_caso_id=cliente_caso_id,
        chave_acesso=evento_dto.chave_acesso,
        tipo_evento=evento_dto.tipo_evento,
        numero_sequencia=evento_dto.numero_sequencia,
        descricao_evento=evento_dto.descricao_evento,
        data_evento=evento_dto.data_evento,
        justificativa=evento_dto.justificativa,
        tp_amb=evento_dto.tp_amb,
        protocolo=evento_dto.protocolo,
        cstat=cstat,
        motivo=evento_dto.motivo,
        arquivo_lote_id=arquivo_lote_id,
        arquivo_origem=caminho_arquivo,
    )
    db.add(evento)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Reupload do mesmo evento (mesma chave+tipo+sequência+cstat, dentro
        # do mesmo caso) -- trata como duplicado, mas ainda tenta aplicar
        # pendente: o primeiro upload pode ter chegado antes da nota
        # existir. Filtra por cliente_caso_id também: sem isso, o mesmo
        # evento importado em dois casos colidiria na unique e o segundo
        # caso leria (e "aplicaria pendente" para) a linha do primeiro.
        evento = (
            db.query(EventoNFe)
            .filter_by(
                cliente_caso_id=cliente_caso_id,
                chave_acesso=evento_dto.chave_acesso,
                tipo_evento=evento_dto.tipo_evento,
                numero_sequencia=evento_dto.numero_sequencia,
                cstat=cstat,
            )
            .one_or_none()
        )
        if evento is None:
            # IntegrityError por outro motivo (FK inválida etc.) -- não é
            # duplicata de verdade, deixa subir para o retry genérico em vez
            # de mascarar como "ja_existente".
            raise
        _aplicar_eventos_pendentes_da_chave(db, evento.chave_acesso, cliente_caso_id)
        return {"status": "ja_existente", "chave_acesso": evento_dto.chave_acesso}

    _aplicar_eventos_pendentes_da_chave(db, evento.chave_acesso, cliente_caso_id)

    return {
        "status": "evento",
        "chave_acesso": evento_dto.chave_acesso,
        "tipo_evento": evento_dto.tipo_evento,
    }


@celery_app.task(
    name="processar_xml_nfe",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def processar_xml_nfe(
    self, caminho_arquivo: str, cnpj_cliente: str, cliente_caso_id: int, arquivo_lote_id: int
) -> dict:
    """
    Processa um único arquivo XML de NF-e OU de evento de NF-e:
    1. Tenta parsing determinístico de nota; se não achar <infNFe>, tenta
       parsing de evento (cancelamento, carta de correção, manifestação).
       Se os dois falharem, reporta o erro do parser de NOTA (é o caminho
       comum, e é a mensagem que o usuário já conhece para XML malformado).
    2. Nota: classifica entrada/saída, persiste nota + itens, e aplica
       qualquer evento pendente daquela chave (pode ter chegado antes).
    3. Evento: persiste em EventoNFe e aplica o efeito na nota se ela já
       existir (ver _aplicar_efeito_evento) -- senão fica órfão até a nota
       chegar num upload futuro.
    4. Atualiza o ArquivoLote correspondente (criado antes do enfileiramento,
       em routes_upload.py) com o desfecho do processamento.

    acks_late+reject_on_worker_lost: se o worker morrer no meio, a mensagem
    volta pra fila e outra execução tenta de novo -- seguro porque
    chave_acesso é UNIQUE e a checagem de `existente` abaixo já trata
    reprocessamento do mesmo arquivo sem duplicar Nota/ItemNota.
    """
    db = SessionLocal()
    resultado: dict | None = None
    try:
        _marcar_processando(db, arquivo_lote_id)

        try:
            nota_dto = parse_nfe_xml(caminho_arquivo)
        except NFeParseError as erro_nota:
            # Escopo estreito de propósito: classificar_tipo (chamado só
            # abaixo, fora deste try) também levanta NFeParseError, e não
            # pode cair aqui -- senão uma nota legítima com CNPJ divergente
            # do cliente do caso seria mandada, errado, para o parser de
            # evento.
            try:
                resultado = _processar_evento(db, caminho_arquivo, cliente_caso_id, arquivo_lote_id)
                return resultado
            except EventoParseError:
                # Nem nota nem evento -- reporta o erro ORIGINAL do parser
                # de nota, que é o caminho comum e a mensagem já conhecida.
                db.rollback()
                resultado = {"status": "erro", "arquivo": caminho_arquivo, "motivo": str(erro_nota)}
                return resultado

        tipo = classificar_tipo(nota_dto, cnpj_cliente)

        existente = db.query(Nota).filter_by(chave_acesso=nota_dto.chave_acesso).first()
        if existente:
            _aplicar_eventos_pendentes_da_chave(db, existente.chave_acesso, cliente_caso_id)
            resultado = {"status": "ja_existente", "chave_acesso": nota_dto.chave_acesso}
            return resultado

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

        _aplicar_eventos_pendentes_da_chave(db, nota.chave_acesso, cliente_caso_id)

        resultado = {
            "status": "ok",
            "chave_acesso": nota_dto.chave_acesso,
            "itens": len(nota_dto.itens),
            "nota_id": nota.id,
        }
        return resultado

    except NFeParseError as exc:
        # classificar_tipo caiu aqui (CNPJ do cliente não bate com emitente
        # nem destinatário) -- determinístico, reprocessar não muda o
        # resultado, então não passa pelo retry abaixo.
        db.rollback()
        resultado = {"status": "erro", "arquivo": caminho_arquivo, "motivo": str(exc)}
        return resultado
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Possivelmente transitório (banco, IO): tenta de novo antes de
        # desistir. Enquanto ainda há tentativas, `resultado` fica None de
        # propósito -- o finally abaixo só grava status terminal quando há
        # um resultado, então uma tentativa que vai se repetir não marca
        # ERRO prematuramente por cima do PROCESSANDO.
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30) from exc
        resultado = {"status": "erro_inesperado", "arquivo": caminho_arquivo, "motivo": str(exc)}
        return resultado
    finally:
        if resultado is not None:
            _atualizar_status_arquivo_lote(db, arquivo_lote_id, resultado)
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


@celery_app.task(name="enviar_email_redefinicao_senha")
def enviar_email_redefinicao_senha(usuario_id: int, token: str) -> dict:
    """
    Envia o e-mail de redefinição de senha, disparado por
    UserManager.on_after_forgot_password (app/core/auth.py) sempre que
    POST /api/auth/forgot-password é chamado para um e-mail cadastrado.

    O link aponta para settings.frontend_base_url + a rota de frontend
    "/redefinir-senha" (Projeto/web/src/paginas/RedefinirSenha).
    """
    db = SessionLocal()
    try:
        usuario = db.get(Usuario, usuario_id)
        if usuario is None:
            return {"status": "erro", "motivo": "usuário não encontrado"}

        link = f"{settings.frontend_base_url}/redefinir-senha?token={token}"
        corpo = (
            f"Olá, {usuario.nome}.\n\n"
            "Recebemos um pedido para redefinir sua senha. Se foi você, "
            f"clique no link abaixo:\n\n{link}\n\n"
            "Se não foi você, ignore este e-mail -- sua senha continua a mesma."
        )
        enviar_email(usuario.email, "Redefinição de senha", corpo)
        return {"status": "ok"}
    finally:
        db.close()


def _normalizar_chave(descricao: str) -> str:
    return descricao.strip().upper()


class _CatalogoEmMemoria:
    """
    Catálogo de canônicos do caso usado como contexto da IA durante uma
    execução de normalizar_produtos_pendentes. Só recebe um canônico novo
    via `registrar`, chamado depois do commit do lote que o criou -- um
    lote que falha e sofre rollback não pode deixar aqui um id que não
    existe mais no banco (a tentativa seguinte o ofereceria à IA como
    candidato válido).
    """

    def __init__(self, canonicos_orm: list[ProdutoCanonico]):
        self.existentes = [
            {"id": c.id, "nome_canonico": c.nome_canonico, "categoria": c.categoria}
            for c in canonicos_orm
        ]
        self.por_id = {c["id"]: c for c in self.existentes}
        # Por nome normalizado (mesma chave de _normalizar_chave) -- usado
        # para não tentar inserir um produto_canonico com nome que já existe
        # (uq_produto_canonico_caso_nome). A IA não coordena "produto novo"
        # entre descrições de um mesmo lote nem enxerga um canônico fora do
        # pré-filtro de embedding, então pode sugerir o mesmo nome como novo
        # mais de uma vez dentro desta mesma execução.
        self.por_nome = {_normalizar_chave(c["nome_canonico"]): c["id"] for c in self.existentes}
        # Só entram no pré-filtro canônicos com embedding do modelo
        # atualmente configurado -- um embedding de modelo antigo é tratado
        # como inexistente, nunca comparado por cosseno contra um vetor de
        # espaço diferente (ver app/models/models.py::ProdutoCanonico.embedding_modelo).
        self.embeddings = {
            c.id: c.embedding
            for c in canonicos_orm
            if c.embedding and c.embedding_modelo == settings.gemini_embedding_model
        }

    def registrar(self, canonico: dict, chave_nome: str, embedding: bytes | None) -> None:
        # Sem isso, o canônico criado (ou reaproveitado de uma colisão) em um
        # lote não apareceria como candidato real (nem na lista cheia, nem no
        # pré-filtro de embedding, nem na dedução por nome) nos lotes
        # seguintes desta mesma execução.
        if canonico["id"] not in self.por_id:
            self.existentes.append(canonico)
            self.por_id[canonico["id"]] = canonico
        self.por_nome[chave_nome] = canonico["id"]
        if embedding is not None:
            self.embeddings[canonico["id"]] = embedding


def _processar_lote_normalizacao(
    db,
    cliente_caso_id: int,
    lote_chaves: list[str],
    descricao_original_por_chave: dict[str, str],
    itens_por_chave: dict[str, list[int]],
    catalogo: _CatalogoEmMemoria,
    usar_filtro_embedding: bool,
    embeddings_descricoes: dict[str, list[float]],
) -> dict:
    """
    Pede à IA as sugestões de um lote e adiciona na sessão os canônicos
    novos e as SugestaoNormalizacao. Não faz commit nem altera `catalogo`:
    quem chama commita e, só então, registra os canônicos devolvidos em
    "canonicos_novos".
    """
    # Relê, a cada tentativa, quais itens do lote já ganharam sugestão: um
    # commit ambíguo (conexão perdida depois de o MySQL efetivar o COMMIT)
    # faria a tentativa seguinte inserir as mesmas sugestões de novo.
    ids_do_lote = [item_id for chave in lote_chaves for item_id in itens_por_chave[chave]]
    ja_sugeridos = {
        item_id
        for (item_id,) in db.query(SugestaoNormalizacao.item_nota_id).filter(
            SugestaoNormalizacao.item_nota_id.in_(ids_do_lote)
        )
    }
    itens_por_chave = {
        chave: [i for i in itens_por_chave[chave] if i not in ja_sugeridos] for chave in lote_chaves
    }
    lote_chaves = [chave for chave in lote_chaves if itens_por_chave[chave]]
    if not lote_chaves:
        return {"sugestoes_criadas": 0, "produtos_canonicos_criados": 0, "canonicos_novos": []}

    descricoes_lote = [descricao_original_por_chave[c] for c in lote_chaves]

    if usar_filtro_embedding:
        ids_candidatos = selecionar_candidatos_similares(
            lote_chaves,
            embeddings_descricoes,
            catalogo.embeddings,
            top_k=TOP_K_CANDIDATOS,
            max_total=MAX_CANDIDATOS_POR_LOTE,
        )
        candidatos_lote = [catalogo.por_id[cid] for cid in ids_candidatos]
    else:
        candidatos_lote = catalogo.existentes

    resultados = sugerir_normalizacao(descricoes_lote, candidatos_lote)
    resultados_por_chave = {_normalizar_chave(r.descricao_original): r for r in resultados}

    # Canônicos novos deste lote, por nome normalizado -- deduplica dentro
    # do lote sem tocar em `catalogo` antes do commit.
    novos_no_lote: dict[str, tuple[dict, bytes | None]] = {}
    sugestoes_criadas = 0
    produtos_canonicos_criados = 0

    for chave in lote_chaves:
        resultado = resultados_por_chave.get(chave)
        if resultado is None:
            continue  # IA não retornou sugestão para essa descrição

        produto_canonico_id = resultado.produto_canonico_id
        if produto_canonico_id is not None and produto_canonico_id not in catalogo.por_id:
            produto_canonico_id = None  # segurança: IA apontou id inexistente

        if produto_canonico_id is None:
            if resultado.novo_produto_canonico is None:
                continue  # sem correspondência e sem produto novo -- ignora

            chave_nome = _normalizar_chave(resultado.novo_produto_canonico.nome_canonico)
            produto_canonico_id = catalogo.por_nome.get(chave_nome)
            if produto_canonico_id is None and chave_nome in novos_no_lote:
                produto_canonico_id = novos_no_lote[chave_nome][0]["id"]

            if produto_canonico_id is None:
                novo = ProdutoCanonico(
                    cliente_caso_id=cliente_caso_id,
                    nome_canonico=resultado.novo_produto_canonico.nome_canonico,
                    categoria=resultado.novo_produto_canonico.categoria,
                )
                novo.embedding = serializar_embedding(gerar_embeddings([novo.nome_canonico])[0])
                novo.embedding_modelo = settings.gemini_embedding_model
                try:
                    with db.begin_nested():
                        db.add(novo)
                        db.flush()  # garante novo.id
                except IntegrityError:
                    # uq_produto_canonico_caso_nome: outra execução
                    # concorrente desta task para o mesmo cliente_caso_id
                    # criou esse nome entre a consulta do catálogo e este
                    # flush. Reusa o canônico existente em vez de abortar
                    # o lote inteiro (e com ele as sugestões já válidas).
                    existente = (
                        db.query(ProdutoCanonico)
                        .filter(
                            ProdutoCanonico.cliente_caso_id == cliente_caso_id,
                            ProdutoCanonico.nome_canonico
                            == resultado.novo_produto_canonico.nome_canonico,
                        )
                        .one()
                    )
                    embedding_existente = (
                        existente.embedding
                        if existente.embedding
                        and existente.embedding_modelo == settings.gemini_embedding_model
                        else None
                    )
                    novos_no_lote[chave_nome] = (
                        {
                            "id": existente.id,
                            "nome_canonico": existente.nome_canonico,
                            "categoria": existente.categoria,
                        },
                        embedding_existente,
                    )
                    produto_canonico_id = existente.id
                else:
                    novos_no_lote[chave_nome] = (
                        {
                            "id": novo.id,
                            "nome_canonico": novo.nome_canonico,
                            "categoria": novo.categoria,
                        },
                        novo.embedding,
                    )
                    produto_canonico_id = novo.id
                    produtos_canonicos_criados += 1

        for item_id in itens_por_chave[chave]:
            db.add(
                SugestaoNormalizacao(
                    item_nota_id=item_id,
                    produto_canonico_sugerido_id=produto_canonico_id,
                    confianca=resultado.confianca,
                    status=StatusRevisao.PENDENTE,
                )
            )
            sugestoes_criadas += 1

    return {
        "sugestoes_criadas": sugestoes_criadas,
        "produtos_canonicos_criados": produtos_canonicos_criados,
        "canonicos_novos": [
            (canonico, chave_nome, embedding)
            for chave_nome, (canonico, embedding) in novos_no_lote.items()
        ],
    }


class _TravaPerdida(Exception):
    """A trava do caso expirou e pode já pertencer a outra execução."""


def _executar_com_tentativas(db, etapa: str, funcao, verificar_trava=None):
    """
    Executa `funcao(tentativa)` e commita. Em erro, faz rollback e tenta de
    novo, até TENTATIVAS_POR_LOTE vezes no total. Devolve (resultado, None)
    no sucesso ou (None, ultimo_erro) quando todas as tentativas falharam.

    `verificar_trava` roda antes de cada tentativa (renovando o TTL) e logo
    antes do commit: se a trava foi perdida, desfaz e propaga _TravaPerdida
    sem tentar de novo -- commitar ali arriscaria duplicar sugestões com a
    execução que assumiu o caso.
    """
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS_POR_LOTE + 1):
        try:
            if verificar_trava is not None:
                verificar_trava()
            resultado = funcao(tentativa)
            if verificar_trava is not None:
                verificar_trava()
            db.commit()
            return resultado, None
        except _TravaPerdida:
            db.rollback()
            raise
        except Exception as exc:  # noqa: BLE001 -- qualquer erro conta como tentativa falha
            db.rollback()
            ultimo_erro = exc
            logger.warning(
                "Normalização: %s falhou (tentativa %d de %d): %r",
                etapa, tentativa, TENTATIVAS_POR_LOTE, exc,
            )
            if tentativa < TENTATIVAS_POR_LOTE:
                indice_espera = min(tentativa - 1, len(ESPERAS_ENTRE_TENTATIVAS) - 1)
                time.sleep(ESPERAS_ENTRE_TENTATIVAS[indice_espera])
    return None, ultimo_erro


def _motivo_falha(erro: Exception) -> str:
    return (
        f"{TENTATIVAS_POR_LOTE} tentativas falharam. Último erro: "
        f"{str(erro) or type(erro).__name__}"
    )


def _assumir_trava(cliente_caso_id: int, task_id: str) -> bool:
    """
    A rota POST /api/produtos/normalizar já adquire a trava com o task_id
    antes de enfileirar; aqui confirma e renova o TTL (o tempo na fila já
    consumiu parte dele). Se a trava expirou na fila, ou a task foi
    enfileirada por outro caminho, tenta adquirir de novo.
    """
    return trava_normalizacao.renovar(cliente_caso_id, task_id) or trava_normalizacao.adquirir(
        cliente_caso_id, task_id
    )


@celery_app.task(bind=True, name="normalizar_produtos_pendentes")
def normalizar_produtos_pendentes(self, cliente_caso_id: int) -> dict:
    """
    Busca itens de nota sem produto_canonico e sem sugestão pendente/já
    revisada, deduplica pela descrição original e pede à IA para sugerir
    um produto canônico (existente ou novo) para cada descrição distinta.
    Cria as SugestaoNormalizacao com status=PENDENTE para revisão humana --
    a IA nunca grava produto_canonico_id diretamente em itens_nota.

    Escopado por cliente_caso_id: tanto os itens pendentes quanto o catálogo
    de canônicos existentes usado como contexto para a IA são restritos ao
    caso, para não misturar vocabulário/dados de produto entre clientes.

    Item de nota CANCELADA fica de fora: não vale gastar chamada de IA
    normalizando produto de uma nota que não conta mais para reconciliação.

    Lote a lote: cada lote de TAMANHO_LOTE_IA descrições é enviado à IA e
    commitado antes do próximo (ver TENTATIVAS_POR_LOTE). Se um lote esgota
    as tentativas, a task para com status "falha_lote" e os lotes anteriores
    ficam salvos -- um novo disparo continua de onde parou, porque os itens
    já com sugestão saem da consulta de pendentes.

    Protegida por trava por caso (app/core/trava_normalizacao.py). Chamada
    direta, fora do Celery (self.request.id é None), roda sem trava.
    """
    task_id = self.request.id
    try:
        # Dentro do try: se o Redis falhar aqui, o finally ainda libera a
        # trava que a rota adquiriu com este task_id (liberar só apaga a
        # trava se ela for deste task_id, então o caminho "ja_em_andamento"
        # não mexe na de outra execução).
        if task_id is not None and not _assumir_trava(cliente_caso_id, task_id):
            return {
                "status": "ja_em_andamento",
                "motivo": "Já existe uma normalização em andamento para este caso.",
            }
        return _normalizar_produtos_pendentes(self, cliente_caso_id, task_id)
    finally:
        if task_id is not None:
            try:
                trava_normalizacao.liberar(cliente_caso_id, task_id)
            except Exception as exc:  # noqa: BLE001
                # Fail-open: sem Redis a trava não sai agora, mas expira
                # sozinha pelo TTL -- não vale trocar o resultado da task
                # (lotes já salvos) por um erro de infraestrutura.
                logger.warning(
                    "Normalização: falha ao liberar trava do caso %s: %r", cliente_caso_id, exc
                )


def _normalizar_produtos_pendentes(task, cliente_caso_id: int, task_id: str | None) -> dict:
    db = SessionLocal()
    try:
        itens_pendentes = (
            db.query(ItemNota.id, ItemNota.descricao_original)
            .join(Nota, Nota.id == ItemNota.nota_id)
            .outerjoin(SugestaoNormalizacao, SugestaoNormalizacao.item_nota_id == ItemNota.id)
            .filter(ItemNota.produto_canonico_id.is_(None))
            .filter(SugestaoNormalizacao.id.is_(None))
            .filter(Nota.cliente_caso_id == cliente_caso_id)
            .filter(Nota.situacao != SituacaoNota.CANCELADA)
            .all()
        )
        if not itens_pendentes:
            return {"status": "ok", "descricoes_unicas": 0, "sugestoes_criadas": 0}

        # Deduplica por descrição normalizada -- poucas descrições distintas,
        # muitas notas repetindo a mesma descrição. Guarda só ids (não
        # objetos ORM): o rollback de um lote que falha expira a sessão.
        itens_por_chave: dict[str, list[int]] = {}
        descricao_original_por_chave: dict[str, str] = {}
        for item_id, descricao in itens_pendentes:
            chave = _normalizar_chave(descricao)
            itens_por_chave.setdefault(chave, []).append(item_id)
            descricao_original_por_chave.setdefault(chave, descricao)

        def _carregar_catalogo() -> _CatalogoEmMemoria:
            return _CatalogoEmMemoria(
                db.query(ProdutoCanonico)
                .filter(ProdutoCanonico.cliente_caso_id == cliente_caso_id)
                .all()
            )

        catalogo = _carregar_catalogo()

        chaves = list(itens_por_chave.keys())
        total_lotes = -(-len(chaves) // TAMANHO_LOTE_IA)  # divisão com arredondamento para cima
        sugestoes_criadas = 0
        produtos_canonicos_criados = 0

        def _falha(numero_lote: int, motivo: str) -> dict:
            return {
                "status": "falha_lote",
                "motivo": motivo,
                "lote_com_falha": numero_lote,
                "total_lotes": total_lotes,
                "lotes_salvos": numero_lote - 1,
                "descricoes_unicas": len(chaves),
                "itens_pendentes": len(itens_pendentes),
                "produtos_canonicos_criados": produtos_canonicos_criados,
                "sugestoes_criadas": sugestoes_criadas,
            }

        def _publicar_progresso(lotes_salvos: int) -> None:
            if task_id is None:
                return
            # Best-effort: progresso é só informativo -- uma oscilação no
            # backend de resultados não pode abortar uma execução saudável.
            try:
                task.update_state(
                    state="PROGRESS",
                    meta={
                        "lotes_salvos": lotes_salvos,
                        "total_lotes": total_lotes,
                        "sugestoes_criadas": sugestoes_criadas,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Normalização: falha ao publicar progresso: %r", exc)

        def _verificar_trava() -> None:
            if task_id is not None and not trava_normalizacao.renovar(cliente_caso_id, task_id):
                raise _TravaPerdida()

        motivo_trava_perdida = (
            "A trava da normalização expirou antes do fim; processamento "
            "interrompido para não duplicar sugestões."
        )

        _publicar_progresso(0)

        # Catálogo pequeno: mantém o comportamento de sempre (lista cheia no
        # prompt, sem custo de embedding). Catálogo grande: gera embedding de
        # cada descrição uma vez, de antemão, e usa como pré-filtro em cada
        # lote -- ver LIMIAR_FILTRO_EMBEDDING acima.
        usar_filtro_embedding = len(catalogo.existentes) > LIMIAR_FILTRO_EMBEDDING
        embeddings_descricoes: dict[str, list[float]] = {}
        if usar_filtro_embedding:
            try:
                vetores, erro = _executar_com_tentativas(
                    db,
                    "embedding das descrições",
                    lambda tentativa: gerar_embeddings(
                        [descricao_original_por_chave[c] for c in chaves], task_type="RETRIEVAL_QUERY"
                    ),
                    _verificar_trava,
                )
            except _TravaPerdida:
                return _falha(1, motivo_trava_perdida)
            if erro is not None:
                return _falha(1, _motivo_falha(erro))
            embeddings_descricoes = dict(zip(chaves, vetores))

        for indice, inicio in enumerate(range(0, len(chaves), TAMANHO_LOTE_IA)):
            numero_lote = indice + 1
            lote_chaves = chaves[inicio : inicio + TAMANHO_LOTE_IA]

            def _tentar_lote(tentativa: int) -> dict:
                nonlocal catalogo
                if tentativa > 1:
                    # O revisor pode ter transferido/apagado um canônico
                    # enquanto a task roda (os lotes anteriores já estão
                    # visíveis) -- recarrega em vez de repetir um erro de FK.
                    catalogo = _carregar_catalogo()
                return _processar_lote_normalizacao(
                    db,
                    cliente_caso_id,
                    lote_chaves,
                    descricao_original_por_chave,
                    itens_por_chave,
                    catalogo,
                    usar_filtro_embedding,
                    embeddings_descricoes,
                )

            try:
                resultado_lote, erro = _executar_com_tentativas(
                    db, f"lote {numero_lote} de {total_lotes}", _tentar_lote, _verificar_trava
                )
            except _TravaPerdida:
                return _falha(numero_lote, motivo_trava_perdida)
            if erro is not None:
                return _falha(numero_lote, _motivo_falha(erro))

            # Só depois do commit o lote passa a valer para os seguintes.
            for canonico, chave_nome, embedding in resultado_lote["canonicos_novos"]:
                catalogo.registrar(canonico, chave_nome, embedding)
            sugestoes_criadas += resultado_lote["sugestoes_criadas"]
            produtos_canonicos_criados += resultado_lote["produtos_canonicos_criados"]
            _publicar_progresso(numero_lote)

        return {
            "status": "ok",
            "descricoes_unicas": len(chaves),
            "itens_pendentes": len(itens_pendentes),
            "total_lotes": total_lotes,
            "produtos_canonicos_criados": produtos_canonicos_criados,
            "sugestoes_criadas": sugestoes_criadas,
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"status": "erro_inesperado", "motivo": str(exc)}
    finally:
        db.close()


@celery_app.task(name="aplicar_eventos_pendentes")
def aplicar_eventos_pendentes(cliente_caso_id: int) -> dict:
    """
    Varre eventos ainda não aplicados (aplicado=False) de um caso e tenta
    aplicar de novo. Fecha a janela que a ordenação de commits de
    processar_xml_nfe não fecha sozinha: um crash entre o commit do evento
    (ou da nota) e o UPDATE que aplica o efeito deixa aplicado=False para
    sempre, sem nada que reprocesse aquela chave -- exceto esta varredura.

    Enfileirada pela rota de upload com um `countdown`, para rodar depois do
    lote assentar (ver app/api/routes_upload.py). Não existe celery-beat
    configurado neste projeto; se um dia existir, esta task é a candidata
    natural a virar periódica.
    """
    db = SessionLocal()
    try:
        pendentes = (
            db.query(EventoNFe.id)
            .filter(EventoNFe.cliente_caso_id == cliente_caso_id, EventoNFe.aplicado.is_(False))
            .all()
        )
        aplicados = 0
        com_falha = 0
        for (evento_id,) in pendentes:
            # Cada evento em try/except próprio -- um erro num evento (ex.:
            # nota apagada, dado inconsistente) não pode abortar a varredura
            # inteira e deixar os demais pendentes sem chance de aplicar.
            try:
                _aplicar_efeito_evento(db, evento_id)
            except Exception:  # noqa: BLE001
                db.rollback()
                com_falha += 1
                continue
            evento = db.get(EventoNFe, evento_id)
            if evento is not None and evento.aplicado:
                aplicados += 1
        return {
            "status": "ok",
            "verificados": len(pendentes),
            "aplicados": aplicados,
            "com_falha": com_falha,
        }
    finally:
        db.close()
