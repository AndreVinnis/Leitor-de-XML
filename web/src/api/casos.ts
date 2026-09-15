import { del, get, patchJson, postJson } from "./cliente";
import type { ClienteCaso } from "./tipos";

export function listarCasos(): Promise<ClienteCaso[]> {
  // Sem barra final: /api/casos, nunca /api/casos/ (ver cliente.ts).
  return get<ClienteCaso[]>("/api/casos");
}

export function criarCaso(
  nomeCliente: string,
  cnpjCliente: string,
  identificacaoCaso?: string
): Promise<ClienteCaso> {
  return postJson<ClienteCaso>("/api/casos", {
    nome_cliente: nomeCliente,
    identificacao_caso: identificacaoCaso || null,
    cnpj_cliente: cnpjCliente,
  });
}

export interface DadosAtualizacaoCaso {
  nome_cliente?: string;
  identificacao_caso?: string | null;
  cnpj_cliente?: string | null;
}

export function atualizarCaso(id: number, dados: DadosAtualizacaoCaso): Promise<ClienteCaso> {
  return patchJson<ClienteCaso>(`/api/casos/${id}`, dados);
}

export function excluirCaso(id: number): Promise<void> {
  return del<void>(`/api/casos/${id}`);
}
