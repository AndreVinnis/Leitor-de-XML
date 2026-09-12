// Wrapper de fetch com as três armadilhas de contrato que
// frontend/api_client.py já documenta para o cliente Python -- ver a seção
// "api/cliente.ts é a peça central" do plano de migração:
//
// 1. 401 centralizado: qualquer 401 limpa a sessão e avisa quem se
//    inscreveu (ContextoAuth), num lugar só.
// 2. Sem normalização de trailing slash: as URLs são montadas literalmente.
//    /api/casos/ (com barra) gera 307 no backend e o redirect pode perder
//    o header Authorization.
// 3. HTTP 200 com erro no corpo (rotas de revisão de sugestão): fora de
//    escopo nesta fase (não há tela de normalização ainda), mas o
//    wrapper já fica pronto para promover isso a exceção quando chegar.

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

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

function obterToken(): string | null {
  try {
    return sessionStorage.getItem("token");
  } catch {
    return null;
  }
}

function limparSessao() {
  try {
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("usuario");
  } catch {
    /* sessionStorage indisponível (aba privada etc.) -- segue o fluxo */
  }
}

interface OpcoesRequisicao {
  method?: string;
  body?: BodyInit;
  headers?: Record<string, string>;
  /** Rotas públicas (login, forgot-password) não devem mandar o Bearer. */
  semAuth?: boolean;
}

async function requisitar<T>(caminho: string, opcoes: OpcoesRequisicao = {}): Promise<T> {
  const headers: Record<string, string> = { ...opcoes.headers };
  const token = obterToken();
  if (token && !opcoes.semAuth) {
    headers.Authorization = `Bearer ${token}`;
  }

  const resposta = await fetch(`${BASE_URL}${caminho}`, {
    method: opcoes.method ?? "GET",
    body: opcoes.body,
    headers,
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

export function postJson<T>(caminho: string, corpo: unknown, opcoes?: OpcoesRequisicao) {
  return post<T>(caminho, {
    ...opcoes,
    headers: { "Content-Type": "application/json", ...opcoes?.headers },
    body: JSON.stringify(corpo),
  });
}
