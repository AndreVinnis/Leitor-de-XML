# Sistema de Análise de Notas Fiscais (XML) com IA

Scaffold inicial do sistema descrito nas Instruções do Projeto. Cobre a
parte **determinística** do pipeline (parsing de XML, banco de dados,
upload em lote) — a normalização por IA, o motor de reconciliação e a
camada de NL→SQL ainda precisam ser implementados.

## Como rodar localmente

1. Copie o arquivo de variáveis de ambiente:
   ```bash
   cp .env.example .env
   ```
   Edite `.env` e coloque sua `ANTHROPIC_API_KEY` (não é usada ainda
   neste scaffold, mas já deixamos o lugar certo para ela).

2. Suba os containers:
   ```bash
   docker compose up --build
   ```
   Isso sobe: `api` (FastAPI, porta 8000), `worker` (Celery), `db` (MySQL,
   porta 3306) e `redis`.

3. Crie as tabelas no banco (por enquanto, sem Alembic ainda — criação
   direta a partir dos models):
   ```bash
   docker compose exec api python -c "from app.core.database import Base, engine; from app.models import models; Base.metadata.create_all(engine)"
   ```

4. Teste se a API está no ar:
   ```bash
   curl http://localhost:8000/health
   ```

5. Faça upload de um lote de XMLs de NF-e:
   ```bash
   curl -X POST http://localhost:8000/api/notas/upload \
     -F "cliente_caso_id=1" \
     -F "cnpj_cliente=12345678000199" \
     -F "arquivos=@nota1.xml" \
     -F "arquivos=@nota2.xml"
   ```
   A resposta é imediata (`status: processando`); cada XML é processado
   em background por um worker Celery. Use o `task_id` retornado para
   consultar o status em `/api/notas/upload/{task_id}/status`.

## O que já está implementado

- Estrutura de containers (Docker Compose): API, worker, MySQL, Redis.
- Modelos de banco (`app/models/models.py`): `notas`, `itens_nota`,
  `produtos_canonicos`, `sugestoes_normalizacao`, `achados_reconciliacao`,
  `clientes_casos`, `usuarios`, `logs_auditoria`.
- Parser determinístico de NF-e com `lxml` (`app/parsers/nfe_parser.py`),
  sem uso de IA — extrai emitente, destinatário, itens, valores, chave de
  acesso.
- Fluxo de upload em lote não-bloqueante: API responde na hora, Celery
  processa cada XML em background (`app/api/routes_upload.py` +
  `app/workers/tasks.py`).

## O que falta (ver "Próximos passos" nas Instruções do Projeto)

1. **Embeddings/busca por similaridade**: decidir entre MySQL 9 (vetor
   nativo), banco vetorial dedicado (Qdrant/Milvus/Chroma) ou similaridade
   calculada em Python contra embeddings salvos como JSON (já há uma
   coluna `embedding` JSON em `produtos_canonicos` como placeholder).
2. **Motor de reconciliação**: lógica pura que cruza entradas x saídas
   por `produto_canonico_id`, calcula saldo e gera `AchadoReconciliacao`.
   Ainda não implementado.
3. **Normalização de produtos via IA**: agrupar `descricao_original`
   parecidas em um `ProdutoCanonico`, gerando `SugestaoNormalizacao` com
   nível de confiança, para revisão humana obrigatória.
4. **Camada NL→SQL**: endpoint que recebe pergunta em linguagem natural,
   usa Claude para gerar SQL, valida contra whitelist de
   tabelas/colunas, executa em conexão somente-leitura, registra em
   `logs_auditoria`.
5. **Camada de explicação**: resumir achados de reconciliação em texto
   para o advogado, sem tirar conclusões jurídicas.
6. **Autenticação e controle de acesso** por cliente/caso
   (`fastapi-users` ou OAuth) — hoje `cliente_caso_id` é aceito sem
   validação de permissão.
7. Migrations com Alembic (hoje as tabelas são criadas via
   `Base.metadata.create_all`, o que não é adequado para produção).

## Estrutura de pastas

```
app/
  api/          endpoints FastAPI
  core/         config e conexão com banco
  models/       modelos SQLAlchemy
  parsers/      parsing determinístico de XML
  schemas/      (a criar) schemas Pydantic de request/response
  workers/      Celery app e tasks
  main.py       ponto de entrada FastAPI
docker/
  Dockerfile
docker-compose.yml
requirements.txt
```
