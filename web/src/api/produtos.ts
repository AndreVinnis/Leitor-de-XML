import { get, patch, postJson } from "./cliente";
import type {
  ListaCanonicos,
  ListaSugestoes,
  ProdutoCanonico,
  ResultadoRevisao,
  ResultadoRevisaoLote,
  StatusRevisao,
} from "./tipos";

interface ParametrosListarSugestoes {
  clienteCasoId: number;
  status?: StatusRevisao | "todos";
  categoria?: string;
  fornecedor?: string;
  busca?: string;
  limit?: number;
  offset?: number;
}

export function listarSugestoes(params: ParametrosListarSugestoes): Promise<ListaSugestoes> {
  const query = new URLSearchParams({ cliente_caso_id: String(params.clienteCasoId) });
  query.set("status", params.status ?? "pendente");
  if (params.categoria) query.set("categoria", params.categoria);
  if (params.fornecedor) query.set("fornecedor", params.fornecedor);
  if (params.busca) query.set("busca", params.busca);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaSugestoes>(`/api/produtos/sugestoes?${query.toString()}`);
}

export function confirmarSugestao(sugestaoId: number): Promise<ResultadoRevisao> {
  return postJson<ResultadoRevisao>(`/api/produtos/sugestoes/${sugestaoId}/confirmar`, {});
}

export function rejeitarSugestao(sugestaoId: number): Promise<ResultadoRevisao> {
  return postJson<ResultadoRevisao>(`/api/produtos/sugestoes/${sugestaoId}/rejeitar`, {});
}

export function corrigirSugestao(sugestaoId: number, produtoCanonicoId: number): Promise<ResultadoRevisao> {
  return postJson<ResultadoRevisao>(`/api/produtos/sugestoes/${sugestaoId}/corrigir`, {
    produto_canonico_id: produtoCanonicoId,
  });
}

export function confirmarSugestoesLote(ids: number[]): Promise<ResultadoRevisaoLote> {
  return postJson<ResultadoRevisaoLote>("/api/produtos/sugestoes/lote/confirmar", { ids });
}

export function rejeitarSugestoesLote(ids: number[]): Promise<ResultadoRevisaoLote> {
  return postJson<ResultadoRevisaoLote>("/api/produtos/sugestoes/lote/rejeitar", { ids });
}

interface ParametrosListarCanonicos {
  clienteCasoId: number;
  categoria?: string;
  busca?: string;
  limit?: number;
  offset?: number;
}

export function listarCanonicos(params: ParametrosListarCanonicos): Promise<ListaCanonicos> {
  const query = new URLSearchParams({ cliente_caso_id: String(params.clienteCasoId) });
  if (params.categoria) query.set("categoria", params.categoria);
  if (params.busca) query.set("busca", params.busca);
  query.set("limit", String(params.limit ?? 50));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaCanonicos>(`/api/produtos/canonicos?${query.toString()}`);
}

export function criarCanonico(
  clienteCasoId: number,
  nomeCanonico: string,
  categoria?: string
): Promise<ProdutoCanonico> {
  return postJson<ProdutoCanonico>("/api/produtos/canonicos", {
    cliente_caso_id: clienteCasoId,
    nome_canonico: nomeCanonico,
    categoria: categoria || null,
  });
}

export function editarCanonico(
  produtoCanonicoId: number,
  campos: { nomeCanonico?: string; categoria?: string }
): Promise<ProdutoCanonico> {
  return patch<ProdutoCanonico>(`/api/produtos/canonicos/${produtoCanonicoId}`, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nome_canonico: campos.nomeCanonico ?? null,
      // "" limpa a categoria no backend; undefined/omitido significa "não mexer" --
      // por isso null aqui (campos.categoria ausente) precisa virar "" quando o
      // chamador quer limpar, nunca ser confundido com "não enviar o campo".
      categoria: campos.categoria ?? null,
    }),
  });
}
