# web/ -- frontend React (produto final)

Este é o frontend definitivo do projeto, migrando gradualmente do Streamlit
em `frontend/` (que continua existindo como ferramenta de teste manual --
ver `frontend/README.md` e a seção correspondente no `CLAUDE.md` do repo).
Vite + React + TypeScript, CSS Modules (sem Tailwind), primitivos do Radix
UI para os componentes que exigem acessibilidade (`Select`, `Toast`).

Fase atual: Login, Criar Conta, Dashboard, Upload de XML, Notas Fiscais,
Produtos (Sugestões da IA + Produtos Canônicos + Itens Vinculados), Consulta,
Aprovação de Cadastros (só para administradores) e Configurações.

## Rodando

Via `docker compose` (recomendado, mesmo fluxo do resto do projeto):

```bash
docker compose up --build web
```

Sobe em http://localhost:5173. Depende da API já estar rodando
(`docker compose up api`).

Local, sem Docker (precisa de Node 22+):

```bash
cd web
cp .env.example .env
npm install
npm run dev
```

## Same origem via proxy do Vite

O React e a API rodam na mesma origem, em dev também (produção já é assim --
ver `Documentação/Deploy e Operação`, "Sirva o React e a API na mesma
origem"). `web/vite.config.ts` tem um `server.proxy` que encaminha `/api/*`
para `http://api:8000` -- o proxy roda no servidor Vite, **dentro** do
container, por isso o alvo é o nome do serviço na rede do Compose, igual o
Streamlit já fazia (`API_BASE_URL=http://api:8000`). O browser só enxerga o
caminho relativo, então `VITE_API_BASE_URL` fica vazio (ver
`docker-compose.yml`, serviço `web`).

## Onde fica a sessão

Cookie HttpOnly (`app/core/auth.py::cookie_backend`), sessão deslizante
(`app/core/sessao_deslizante.py` reemite o cookie quando passa da metade da
vida). Nenhum código em `src/` lê ou escreve o segredo da sessão -- o browser
manda o cookie sozinho em toda requisição same-origin. `sessionStorage` ainda
guarda o objeto `usuario` (não é segredo, só evita um round-trip a
`/api/auth/users/me` a cada F5).

Toda requisição que muda estado por cookie -- login por cookie incluído --
precisa do header `X-Requested-With: XMLHttpRequest` (`src/api/cliente.ts`
já manda em toda chamada; ver `app/core/csrf.py` para o porquê: `SameSite`
não cobre um POST form-urlencoded cross-site nem impede o `Set-Cookie` de um
login forjado).

## Armadilhas de contrato herdadas da API (ver `src/api/cliente.ts`)

1. **401 é o caminho normal, não uma excecão rara.** A sessão desliza
   sozinha enquanto usada, mas ainda expira se ficar ociosa; `POST
   /api/auth/cookie/logout` invalida de verdade (o `/jwt` antigo, usado só
   pelo Streamlit/testes, continua no-op). Qualquer 401 limpa a sessão e
   volta pro login, tratado num lugar só.
2. **Sem barra final nas URLs de coleção** (`/api/casos`, `/api/notas`,
   `/api/consulta`). Com barra, o backend responde 307 e o redirect pode
   perder o cookie/header de autenticação.
3. **200 com erro no corpo** nas rotas de revisão de sugestão de produto
   (`app/api/routes_produtos.py`). A tela de Produtos (`src/paginas/Produtos/`)
   trata isso na própria página, inspecionando o campo `status` do retorno --
   o wrapper de fetch (`api/cliente.ts`) não promove esse caso a exceção.

## Estrutura

```
src/
  api/         cliente de fetch + um módulo por recurso (auth, casos, dashboard, notas)
  auth/        ContextoAuth (sessão por cookie + usuário) e RotaProtegida
  casos/       ContextoCaso (lista de casos, caso ativo vem da URL)
  componentes/ Botao, CampoTexto, Card, CardMetrica, Tabela, Paginacao, Select, Toast
  layout/      LayoutApp (sidebar + seletor de caso, espelha a sidebar do Streamlit)
  paginas/     uma pasta por tela (Login, Dashboard, Produtos, Consulta, ...)
  estilos/     tokens.css (variáveis de design) + global.css
```

`estilos/tokens.css` já tem os valores reais do protótipo Figma (conferidos
via MCP do Figma). Trocar os valores lá não deveria exigir tocar em nenhum
componente.
