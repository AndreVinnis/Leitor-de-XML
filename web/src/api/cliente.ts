// Wrapper de fetch com as armadilhas de contrato que
// frontend/api_client.py já documenta para o cliente Python -- ver a seção
// "api/cliente.ts é a peça central" do plano de migração:
//
// 1. 401 centralizado: qualquer 401 limpa a sessão e avisa quem se
//    inscreveu (ContextoAuth), num lugar só.
// 2. Sem normalização de trailing slash: as URLs são montadas literalmente.
//    /api/casos/ (com barra) gera 307 no backend e o redirect pode perder
//    cabeçalho/cookie de autenticação.
// 3. HTTP 200 com erro no corpo (rotas de revisão de sugestão): fora de
//    escopo nesta fase (não há tela de normalização ainda), mas o
//    wrapper já fica pronto para promover isso a exceção quando chegar.
// 4. Sessão por cookie HttpOnly (app/core/auth.py::cookie_backend): nenhum
//    código aqui lê ou escreve o token -- o browser manda o cookie sozinho
//    em toda requisição same-origin (credentials "same-origin", já o
//    default do fetch, mas explícito por clareza). O header abaixo é só a
//    prova de que a chamada veio de JS same-origin (anti-CSRF, ver
//    app/core/csrf.py) -- não é segredo, pode estar hardcoded no bundle.

const BASE_URL = import.meta.env.VITE_API_BASE_URL;
const HEADER_ANTI_CSRF = "X-Requested-With";
const VALOR_HEADER_ANTI_CSRF = "XMLHttpRequest";

export class ErroApi extends Error {
  status: number;

  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.status = status;
  }
}

// A tela de login ainda não existe quando este módulo é carregado, então o
// callback de "sessão expirou" é registrado depois, pelo ContextoAuth.
let aoSessaoExpirar: (() => void) | null = null;

export function registrarCallbackSessaoExpirada(callback: () => void) {
  aoSessaoExpirar = callback;
}

function limparSessao() {
  try {
    sessionStorage.removeItem("usuario");
  } catch {
    /* sessionStorage indisponível (aba privada etc.) -- segue o fluxo */
  }
}

interface OpcoesRequisicao {
  method?: string;
  body?: BodyInit;
  headers?: Record<string, string>;
}

async function requisitar<T>(caminho: string, opcoes: OpcoesRequisicao = {}): Promise<T> {
  const headers: Record<string, string> = {
    [HEADER_ANTI_CSRF]: VALOR_HEADER_ANTI_CSRF,
    ...opcoes.headers,
  };

  const resposta = await fetch(`${BASE_URL}${caminho}`, {
    method: opcoes.method ?? "GET",
    body: opcoes.body,
    headers,
    credentials: "same-origin",
  });

  if (resposta.status === 401) {
    limparSessao();
    aoSessaoExpirar?.();
    throw new ErroApi(401, "Sua sessão expirou. Faça login novamente.");
  }

  if (!resposta.ok) {
    let detalhe = `Erro ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      detalhe = typeof corpo.detail === "string" ? corpo.detail : JSON.stringify(corpo.detail ?? corpo);
    } catch {
      /* corpo de erro não é JSON -- mantém a mensagem genérica acima */
    }
    throw new ErroApi(resposta.status, detalhe);
  }

  if (resposta.status === 204) {
    return undefined as T;
  }
  return (await resposta.json()) as T;
}

export function get<T>(caminho: string, opcoes?: OpcoesRequisicao) {
  return requisitar<T>(caminho, { ...opcoes, method: "GET" });
}

export function post<T>(caminho: string, opcoes?: OpcoesRequisicao) {
  return requisitar<T>(caminho, { ...opcoes, method: "POST" });
}

export function patch<T>(caminho: string, opcoes?: OpcoesRequisicao) {
  return requisitar<T>(caminho, { ...opcoes, method: "PATCH" });
}

export function del<T>(caminho: string, opcoes?: OpcoesRequisicao) {
  return requisitar<T>(caminho, { ...opcoes, method: "DELETE" });
}

export function postJson<T>(caminho: string, corpo: unknown, opcoes?: OpcoesRequisicao) {
  return post<T>(caminho, {
    ...opcoes,
    headers: { "Content-Type": "application/json", ...opcoes?.headers },
    body: JSON.stringify(corpo),
  });
}

export function patchJson<T>(caminho: string, corpo: unknown, opcoes?: OpcoesRequisicao) {
  return patch<T>(caminho, {
    ...opcoes,
    headers: { "Content-Type": "application/json", ...opcoes?.headers },
    body: JSON.stringify(corpo),
  });
}
