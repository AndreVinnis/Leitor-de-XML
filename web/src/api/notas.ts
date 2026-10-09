import { baixarArquivoPost, get, post } from "./cliente";
import type {
  ListaLotesComErro,
  ListaIdsNotas,
  ListaNotas,
  NotaDetalhe,
  ProgressoLote,
  StatusNota,
  TipoNota,
  UploadNotasResposta,
} from "./tipos";

interface ParametrosListarNotas {
  clienteCasoId: number;
  status?: StatusNota;
  tipo?: TipoNota;
  q?: string;
  dataInicio?: string;
  dataFim?: string;
  limit?: number;
  offset?: number;
}

export function listarNotas(params: ParametrosListarNotas): Promise<ListaNotas> {
  const query = new URLSearchParams({ cliente_caso_id: String(params.clienteCasoId) });
  if (params.status) query.set("status", params.status);
  if (params.tipo) query.set("tipo", params.tipo);
  if (params.q) query.set("q", params.q);
  if (params.dataInicio) query.set("data_inicio", params.dataInicio);
  if (params.dataFim) query.set("data_fim", params.dataFim);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaNotas>(`/api/notas?${query.toString()}`);
}

type FiltrosNotas = Pick<ParametrosListarNotas, "clienteCasoId" | "status" | "tipo" | "q" | "dataInicio" | "dataFim">;

/** Ids de todas as notas do filtro (o backend limita a 500) -- alimenta o "selecionar todas". */
export function listarIdsNotas(params: FiltrosNotas): Promise<ListaIdsNotas> {
  const query = new URLSearchParams({ cliente_caso_id: String(params.clienteCasoId) });
  if (params.status) query.set("status", params.status);
  if (params.tipo) query.set("tipo", params.tipo);
  if (params.q) query.set("q", params.q);
  if (params.dataInicio) query.set("data_inicio", params.dataInicio);
  if (params.dataFim) query.set("data_fim", params.dataFim);
  return get<ListaIdsNotas>(`/api/notas/ids?${query.toString()}`);
}

/** Baixa o XML (1 nota) ou um ZIP (várias). Devolve quantos XMLs não foram encontrados no servidor. */
export function baixarNotas(ids: number[]): Promise<number> {
  return baixarArquivoPost("/api/notas/download", { ids }, ids.length === 1 ? "nota.xml" : "notas_fiscais.zip");
}

export type FormatoDownload = "xml" | "danfe";

// Mesmo teto do backend (LIMITE_DOWNLOAD_DANFE em app/api/routes_notas.py).
export const LIMITE_DOWNLOAD_DANFE = 200;

/**
 * Baixa o DANFE em PDF (1 nota) ou um ZIP com um PDF por nota (várias).
 * Devolve quantas notas ficaram de fora (sem XML no servidor ou XML que não gera DANFE).
 */
export function baixarDanfes(ids: number[]): Promise<number> {
  return baixarArquivoPost("/api/notas/danfe", { ids }, ids.length === 1 ? "DANFE.pdf" : "danfes.zip");
}

export function obterNota(notaId: number): Promise<NotaDetalhe> {
  return get<NotaDetalhe>(`/api/notas/${notaId}`);
}

export function progressoLote(loteId: string): Promise<ProgressoLote> {
  return get<ProgressoLote>(`/api/notas/lotes/${loteId}`);
}

interface ParametrosListarLotesComErro {
  clienteCasoId?: number;
  limit?: number;
  offset?: number;
}

export function listarLotesComErro(params: ParametrosListarLotesComErro = {}): Promise<ListaLotesComErro> {
  const query = new URLSearchParams();
  if (params.clienteCasoId !== undefined) query.set("cliente_caso_id", String(params.clienteCasoId));
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaLotesComErro>(`/api/notas/lotes?${query.toString()}`);
}

// Mesmos tetos do backend (LIMITE_ARQUIVOS_POR_LOTE em app/api/routes_upload.py,
// upload_max_bytes_por_arquivo em app/core/config.py). O de bytes por lote fica
// abaixo dos 500 MB do backend de propósito: o LimiteTamanhoCorpoMiddleware
// conta o corpo inteiro (com o overhead do multipart) e só tem 1 MB de folga.
export const LIMITE_ARQUIVOS_POR_LOTE = 999;
export const LIMITE_BYTES_POR_ARQUIVO = 5 * 1024 * 1024;
export const LIMITE_BYTES_POR_LOTE = 480 * 1024 * 1024;

/**
 * Divide os arquivos em partes que cabem num upload cada (até
 * LIMITE_ARQUIVOS_POR_LOTE arquivos e LIMITE_BYTES_POR_LOTE bytes), na ordem
 * recebida. Cada parte vira um Lote próprio no backend.
 */
export function dividirEmPartes(arquivos: File[]): File[][] {
  const partes: File[][] = [];
  let atual: File[] = [];
  let bytesAtual = 0;
  for (const arquivo of arquivos) {
    const cheia =
      atual.length >= LIMITE_ARQUIVOS_POR_LOTE || bytesAtual + arquivo.size > LIMITE_BYTES_POR_LOTE;
    if (cheia && atual.length > 0) {
      partes.push(atual);
      atual = [];
      bytesAtual = 0;
    }
    atual.push(arquivo);
    bytesAtual += arquivo.size;
  }
  if (atual.length > 0) partes.push(atual);
  return partes;
}

export function uploadNotas(
  clienteCasoId: number,
  cnpjCliente: string,
  arquivos: File[]
): Promise<UploadNotasResposta> {
  const form = new FormData();
  form.append("cliente_caso_id", String(clienteCasoId));
  form.append("cnpj_cliente", cnpjCliente);
  // Campo repetido por arquivo, exatamente como o Streamlit já faz em
  // api_client.py -- é assim que o FastAPI recebe `arquivos: list[UploadFile]`.
  arquivos.forEach((arquivo) => form.append("arquivos", arquivo));
  // Sem Content-Type manual: o browser define o boundary do multipart.
  return post<UploadNotasResposta>("/api/notas/upload", { body: form });
}
