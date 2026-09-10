import { get, postJson } from "./cliente";
import type { ClienteCaso } from "./tipos";

export function listarCasos(): Promise<ClienteCaso[]> {
  // Sem barra final: /api/casos, nunca /api/casos/ (ver cliente.ts).
  return get<ClienteCaso[]>("/api/casos");
}

export function criarCaso(nomeCliente: string, identificacaoCaso?: string): Promise<ClienteCaso> {
  return postJson<ClienteCaso>("/api/casos", {
    nome_cliente: nomeCliente,
    identificacao_caso: identificacaoCaso || null,
  });
}
