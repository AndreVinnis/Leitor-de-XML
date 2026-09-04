# Front-end de teste manual (Streamlit)

Este não é o front-end definitivo do produto -- é uma ferramenta local para
testar, tela por tela, os fluxos que atravessam vários endpoints da API
(fazer upload → acompanhar o lote → normalizar → revisar sugestões), coisa
que pelo Swagger só dá para exercitar um endpoint de cada vez. Segue o
layout das 4 telas do protótipo Figma: Login, Criar Conta, Dashboard e
Normalização de Produtos.

## Como rodar

Só existe um jeito suportado: pelo container Docker, como parte do
`docker compose` do projeto (não há um fluxo de `streamlit run` local fora
do container documentado). A partir de `Projeto/`:

```bash
docker compose up --build
```

Isso sobe também o serviço `frontend` em http://localhost:8501, além dos
serviços já existentes (`api` em :8000, `worker`, `db`, `redis`, `mailhog`
em :8025). O volume `.:/code` faz o Streamlit recarregar sozinho ao detectar
mudança em qualquer arquivo de `frontend/`, sem precisar rebuildar a imagem
-- igual ao `--reload` que a `api` já usa.

## Roteiro de teste manual

1. Subir tudo: `docker compose up --build` e, em outro terminal, aplicar as
   migrações: `docker compose exec api alembic upgrade head`.
2. Criar um administrador:
   ```bash
   docker compose exec api python -m app.scripts.criar_admin --nome "X" --email a@b.com
   ```
3. Abrir http://localhost:8501. Se a tela de login não conseguir falar com
   a API, confira de dentro do container que o hostname resolve:
   ```bash
   docker compose exec frontend python -c "import requests; print(requests.get('http://api:8000/health').json())"
   ```
4. Criar conta pelo app → abrir o MailHog em http://localhost:8025 → clicar
   no link de aprovação (ele aponta para `localhost:8000`, que funciona no
   navegador do host, mesmo o e-mail tendo sido "enviado" de dentro da rede
   do Compose) → voltar ao app e logar.
5. Criar um caso pela sidebar (seletor "Cliente / caso" + expander "+ Novo
   caso"); gerar XMLs de teste com `Projeto/tests/gerar_lote_teste.py` e
   subir pelo Dashboard; acompanhar o progresso do lote até concluir;
   conferir os 3 cards e a tabela de notas recentes.
6. Disparar a normalização na tela "Normalização de Produtos" (exige
   `GEMINI_API_KEY` configurada no `.env` da API); revisar as sugestões
   usando os filtros de aba/categoria/fornecedor/busca; confirmar uma
   sugestão individualmente (botão ✓ da linha) e um conjunto em lote
   (checkboxes + "Confirmar selecionados"); conferir a mudança de status ao
   alternar entre as abas Pendentes/Aprovados/Rejeitados.

## Detalhes que valem a pena saber testando

- **Login com cadastro pendente**: falha com a mesma mensagem de "e-mail ou
  senha inválidos" de uma senha errada -- a tela avisa isso explicitamente,
  mas se acontecer, o motivo real costuma ser aprovação pendente.
- **Sessão expira em 1 hora**: o token JWT dura 3600s; qualquer chamada à
  API que volte 401 já limpa a sessão e manda de volta para o login
  automaticamente (tratamento centralizado em `api_client.py`).
- **Revisão de sugestão "com sucesso" no HTTP, mas com erro no corpo**: as
  4 rotas de confirmar/rejeitar (unitárias e em lote) sempre respondem 200;
  um erro (ex.: sugestão inexistente) aparece só no corpo da resposta. A
  tela de normalização já trata isso, inspecionando o campo `status` de
  cada resultado -- não é um bug se você ver isso no código, é o contrato
  real da API.

## Estrutura

```
frontend/
  streamlit_app.py   # entrada única: inicializa sessão, roteia entre telas, sidebar autenticada
  api_client.py       # uma função por endpoint da API, com o tratamento de erro/401 centralizado
  paginas/
    login.py           # 01 - Login
    criar_conta.py      # 02 - Criar Conta
    dashboard.py        # 03 - Home (Dashboard)
    normalizacao.py     # 04 - Normalização de Produtos
  requirements.txt    # streamlit + requests, versões fixas
```

O roteamento entre telas é feito só por `st.session_state["pagina"]`, e não
pelo diretório mágico `pages/` do Streamlit: com `pages/`, cada arquivo
ganha uma URL própria e dá para navegar direto para ela, contornando a tela
de login.
