import { get, post } from "./cliente";
import type { ListaNotas, ProgressoLote, StatusNota, UploadNotasResposta } from "./tipos";

interface ParametrosListarNotas {
  clienteCasoId: number;
  status?: StatusNota;
  limit?: number;
  offset?: number;
}

export function listarNotas(params: ParametrosListarNotas): Promise<ListaNotas> {
  const query = new URLSearchParams({ cliente_caso_id: String(params.clienteCasoId) });
  if (params.status) query.set("status", params.status);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaNotas>(`/api/notas?${query.toString()}`);
}

export function progressoLote(loteId: string): Promise<ProgressoLote> {
  return get<ProgressoLote>(`/api/notas/lotes/${loteId}`);
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
