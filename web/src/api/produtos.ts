import { get, patch, postJson } from "./cliente";
import type {
  DisparoNormalizacao,
  ListaCanonicos,
  ListaItensVinculados,
  ListaSugestoes,
  ProdutoCanonico,
  ResultadoRevisao,
  ResultadoRevisaoLote,
  ResultadoTransferencia,
  StatusNormalizacao,
  StatusRevisao,
  TipoNota,
} from "./tipos";

export function dispararNormalizacao(clienteCasoId: number): Promise<DisparoNormalizacao> {
  return postJson<DisparoNormalizacao>("/api/produtos/normalizar", { cliente_caso_id: clienteCasoId });
}

export function statusNormalizacao(taskId: string): Promise<StatusNormalizacao> {
  return get<StatusNormalizacao>(`/api/produtos/normalizar/${taskId}/status`);
}

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

interface ParametrosListarItensVinculados {
  produtoCanonicoId: number;
  tipo?: TipoNota;
  fornecedor?: string;
  dataInicio?: string;
  dataFim?: string;
  busca?: string;
  limit?: number;
  offset?: number;
}

export function listarItensVinculados(
  params: ParametrosListarItensVinculados
): Promise<ListaItensVinculados> {
  const query = new URLSearchParams();
  if (params.tipo) query.set("tipo", params.tipo);
  if (params.fornecedor) query.set("fornecedor", params.fornecedor);
  if (params.dataInicio) query.set("data_inicio", params.dataInicio);
  if (params.dataFim) query.set("data_fim", params.dataFim);
  if (params.busca) query.set("busca", params.busca);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaItensVinculados>(
    `/api/produtos/canonicos/${params.produtoCanonicoId}/itens?${query.toString()}`
  );
}

/**
 * Reatribui manualmente um item já vinculado a outro produto canônico --
 * ação de edição na tela "Itens Vinculados", diferente de corrigirSugestao
 * (que só vale enquanto a sugestão de origem ainda está pendente).
 */
export function reatribuirItem(
  itemNotaId: number,
  produtoCanonicoId: number
): Promise<{ id: number; produto_canonico_id: number }> {
  return patch<{ id: number; produto_canonico_id: number }>(`/api/produtos/itens/${itemNotaId}`, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ produto_canonico_id: produtoCanonicoId }),
  });
}

/**
 * Absorve o produto canônico de ORIGEM em outro do mesmo caso: itens,
 * sugestões e achados são repontados para o destino e a origem é excluída.
 * Irreversível -- a UI sempre confirma antes (ModalTransferirCanonico).
 */
export function transferirCanonico(
  produtoCanonicoId: number,
  destinoId: number
): Promise<ResultadoTransferencia> {
  return postJson<ResultadoTransferencia>(
    `/api/produtos/canonicos/${produtoCanonicoId}/transferir`,
    { destino_id: destinoId }
  );
}
