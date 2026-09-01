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
   Edite `.env` e coloque sua `GEMINI_API_KEY` (não é usada ainda
   neste scaffold, mas já deixamos o lugar certo para ela).

2. Suba os containers:
   ```bash
   docker compose up --build
   ```
   Isso sobe: `api` (FastAPI, porta 8000), `worker` (Celery), `db` (MySQL,
   porta 3306), `redis` e `mailhog` (captura os e-mails enviados em dev —
   veja em http://localhost:8025, nenhum e-mail sai de verdade).

3. Crie/atualize as tabelas do banco rodando as migrations do Alembic:
   ```bash
   docker compose exec api alembic upgrade head
   ```
   Se seu banco já existia de antes do Alembic ser configurado (criado via
   `Base.metadata.create_all`, como neste projeto até pouco atrás) e o
   schema já bate com a migration `0001` (`migrations/versions/..._inicial.py`),
   marque-o como já aplicado em vez de rodar `upgrade head` direto:
   ```bash
   docker compose exec api alembic stamp <revision_da_migration_0001>
   docker compose exec api alembic upgrade head
   ```
   Em um banco novo (do zero), `alembic upgrade head` sozinho já cria tudo.

4. Crie o primeiro usuário administrador (precisa existir alguém pra
   aprovar os próximos cadastros):
   ```bash
   docker compose exec api python -m app.scripts.criar_admin --nome "Seu Nome" --email admin@escritorio.com
   ```

5. Teste se a API está no ar:
   ```bash
   curl http://localhost:8000/health
   ```

6. Cadastre um usuário comum (fica pendente até um admin aprovar/reprovar
   pelo link que chega em http://localhost:8025):
   ```bash
   curl -X POST http://localhost:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"nome": "Fulano", "email": "fulano@escritorio.com", "password": "senha-forte"}'
   ```

7. Faça upload de um lote de XMLs de NF-e:
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
- Autenticação e cadastro com aprovação (`fastapi-users`, `app/core/auth.py`
  + `app/api/routes_auth.py`): dois níveis de usuário (`comum` /
  `administrador`); todo novo cadastro nasce pendente e não consegue
  logar; os administradores já aprovados recebem um e-mail com links de
  aprovar/reprovar (token assinado, uso único, expira em 30 min — ver
  `app/core/tokens.py`); o usuário recebe um e-mail avisando o resultado.
  Falta: tela/painel administrativo (hoje a decisão só acontece pelo link
  do e-mail).
- Migrations com Alembic (`migrations/`): `0001` recria o schema que já
  existia (criado originalmente via `create_all`), `0002` aplica as
  mudanças de autenticação em `usuarios`. Novo ambiente: `alembic upgrade
  head` cria tudo do zero. Banco antigo já existente: ver o passo 3 em
  "Como rodar localmente".

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
6. **Controle de acesso por cliente/caso** — login e cadastro com
   aprovação já existem (item acima), mas `cliente_caso_id` ainda é
   aceito nas rotas de notas/produtos sem checar se o usuário logado tem
   permissão sobre aquele cliente/caso.

## Estrutura de pastas

```
app/
  api/          endpoints FastAPI
  core/         config, conexão com banco, auth, e-mail, tokens
  models/       modelos SQLAlchemy
  parsers/      parsing determinístico de XML
  schemas/      schemas Pydantic de request/response
  scripts/      scripts avulsos (ex: criar_admin)
  workers/      Celery app e tasks
  main.py       ponto de entrada FastAPI
docker/
  Dockerfile
migrations/     Alembic (env.py + versions/)
alembic.ini
docker-compose.yml
requirements.txt
```
