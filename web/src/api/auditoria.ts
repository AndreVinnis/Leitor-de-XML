import { get } from "./cliente";
import type { ListaLogsAuditoria } from "./tipos";

interface ParametrosListarLogsAuditoria {
  dataInicio?: string;
  dataFim?: string;
  limit?: number;
  offset?: number;
}

export function listarLogsAuditoria(params: ParametrosListarLogsAuditoria = {}): Promise<ListaLogsAuditoria> {
  const query = new URLSearchParams();
  if (params.dataInicio) query.set("data_inicio", params.dataInicio);
  if (params.dataFim) query.set("data_fim", params.dataFim);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaLogsAuditoria>(`/api/logs-auditoria?${query.toString()}`);
}
