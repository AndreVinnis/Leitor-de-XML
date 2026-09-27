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

1. ~~Embeddings/busca por similaridade~~ — **implementado**: pré-filtro por
   embedding (Gemini) + similaridade de cosseno calculada em Python/numpy
   sobre a coluna `embedding` (JSON) de `produtos_canonicos`, usado só
   quando o catálogo de canônicos do caso é grande demais para caber
   inteiro no prompt (ver `app/ai/embeddings.py` e
   `app/workers/tasks.py::normalizar_produtos_pendentes`). Sem MySQL 9 e
   sem banco vetorial dedicado.
2. ~~Eventos de NF-e (cancelamento, carta de correção, manifestação)~~ —
   **implementado**: `app/parsers/evento_parser.py` lê o XML de evento
   (formato diferente do XML da nota) e `app/workers/tasks.py` persiste
   todo evento em `EventoNFe`, com cancelamento (`tpEvento 110111`,
   homologado pelo Sefaz) marcando `Nota.situacao = cancelada`. Ver
   CLAUDE.md, seção "Eventos de NF-e", para o contrato completo (evento
   órfão, guarda de `cStat`/`tpAmb`, invariante de concorrência).
3. **Motor de reconciliação**: lógica pura que cruza entradas x saídas
   por `produto_canonico_id`, calcula saldo e gera `AchadoReconciliacao`.
   Ainda não implementado. Precisa filtrar `Nota.situacao = autorizada`,
   senão nota cancelada infla o lado entrada ou saída.
4. **Normalização de produtos via IA**: agrupar `descricao_original`
   parecidas em um `ProdutoCanonico`, gerando `SugestaoNormalizacao` com
   nível de confiança, para revisão humana obrigatória.
5. ~~Camada NL→SQL~~ — **implementado**: `POST /api/consulta` traduz a
   pergunta em um plano de até 3 SQLs (Gemini), valida cada um contra a
   whitelist de tabelas/colunas (`app/core/sql_seguranca.py`), executa
   escopado por `cliente_caso_id` e registra tudo em `logs_auditoria`. Para
   pergunta objetiva ("quantos itens...", "qual o valor total..."), devolve
   também uma frase-resposta em PT-BR com os valores preenchidos
   deterministicamente pelo backend (`app/core/resposta_consulta.py` — a IA
   nunca escreve o número) e a tabela de fontes (notas/itens) usada no
   cálculo. Falta conexão de banco somente leitura como camada extra de
   defesa (ver limitação anotada em `app/core/sql_seguranca.py`).
6. **Camada de explicação**: resumir achados de reconciliação em texto
   para o advogado, sem tirar conclusões jurídicas.
7. **Controle de acesso por cliente/caso** — login e cadastro com
   aprovação já existem (item acima), mas `cliente_caso_id` ainda é
   aceito nas rotas de notas/produtos sem checar se o usuário logado tem
   permissão sobre aquele cliente/caso.
8. **Endurecer `app/core/sql_seguranca.py::validar_e_finalizar_sql`** —
   revisão crítica (2026-09-26) achou bypasses que o validador atual
   aprova sem erro:
   - `... WHERE situacao='autorizada' OR cliente_caso_id = :cliente_caso_id`
     devolve dados de todos os casos (o validador só exige que o
     placeholder *apareça* na query, não que ele efetivamente filtre).
   - `... -- :cliente_caso_id` joga o placeholder para dentro de um
     comentário SQL (passa na checagem de presença, mas não filtra nada;
     de quebra comenta também o `LIMIT` que o validador tentaria
     acrescentar).
   - Uma consulta que não usa a tabela `notas` diretamente (ex.: filtra
     `itens_nota` por uma subquery em `produtos_canonicos`) escapa da
     exigência de mencionar `situacao`, deixando nota cancelada entrar em
     soma/contagem.
   - Falta a conexão de banco somente leitura (grant `SELECT`-only) como
     camada extra de defesa, já anotada como limitação conhecida no
     docstring do módulo.

   Prioridade alta antes de rodar com dado real de cliente — afeta toda
   consulta NL→SQL (item 5), não só perguntas objetivas.

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
