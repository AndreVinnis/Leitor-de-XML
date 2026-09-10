# web/ -- frontend React (produto final)

Este é o frontend definitivo do projeto, migrando gradualmente do Streamlit
em `frontend/` (que continua existindo como ferramenta de teste manual --
ver `frontend/README.md` e a seção correspondente no `CLAUDE.md` do repo).
Vite + React + TypeScript, CSS Modules (sem Tailwind), primitivos do Radix
UI para os componentes que exigem acessibilidade (`Select`, `Toast`).

Fase atual: Login + Dashboard. Ver
`C:\Users\andre\.claude\plans\quero-come-ar-a-migra-o-hashed-pixel.md` para
o plano completo e as fases seguintes.

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

## Armadilha de `VITE_API_BASE_URL`: o inverso do Streamlit

O serviço `frontend` (Streamlit) roda **dentro** do container e usa
`API_BASE_URL=http://api:8000` -- é o nome do serviço na rede do Compose.

O React roda **no browser do host**, não dentro do container. `api` não
resolve para o browser, então `VITE_API_BASE_URL` precisa ser
`http://localhost:8000`. Copiar o padrão do `frontend` aqui dá um erro de
rede difícil de diagnosticar (o container até builda e sobe normalmente --
o erro só aparece no fetch, no browser).

## Onde fica o token

`sessionStorage`, não `localStorage` nem cookie. Sobrevive ao F5 na mesma
aba, morre quando a aba fecha, não vaza para outras abas. É o meio-termo
razoável enquanto o backend autentica por Bearer
(`app/core/auth.py::BearerTransport`). Migrar para cookie httpOnly exigiria
`allow_credentials=True` no CORS e proteção CSRF -- fora de escopo por
enquanto.

## Armadilhas de contrato herdadas da API (ver `src/api/cliente.ts`)

1. **401 é o caminho normal, não uma excecão rara.** O JWT dura 3600s e não
   há refresh token; `POST /api/auth/jwt/logout` é um 204 no-op. Qualquer
   401 limpa a sessão e volta pro login, tratado num lugar só.
2. **Sem barra final nas URLs de coleção** (`/api/casos`, `/api/notas`,
   `/api/consulta`). Com barra, o backend responde 307 e o redirect pode
   perder o header `Authorization`.
3. **200 com erro no corpo** nas rotas de revisão de sugestão de produto
   (`app/api/routes_produtos.py`). Ainda não há tela que use isso (chega na
   fase de Normalização), mas o wrapper de fetch já está pronto pra
   promover esse caso a exceção.

## Estrutura

```
src/
  api/         cliente de fetch + um módulo por recurso (auth, casos, dashboard, notas)
  auth/        ContextoAuth (token + usuário) e RotaProtegida
  casos/       ContextoCaso (lista de casos, caso ativo vem da URL)
  componentes/ Botao, CampoTexto, Card, CardMetrica, Tabela, Paginacao, Select, Toast
  layout/      LayoutApp (sidebar + seletor de caso, espelha a sidebar do Streamlit)
  paginas/     uma pasta por tela (Login, Dashboard)
  estilos/     tokens.css (variáveis de design) + global.css
```

`estilos/tokens.css` está com uma paleta **placeholder**, ainda sem os
valores reais do protótipo Figma (aguardando o MCP do Figma ser conectado --
ver Etapa 3 do plano). Trocar os valores lá não deveria exigir tocar em
nenhum componente.
