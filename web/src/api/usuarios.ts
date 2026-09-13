import { get, patch, postJson } from "./cliente";
import type {
  ListaUsuarios,
  ResultadoDecisaoCadastro,
  ResultadoDecisaoCadastroLote,
  RoleUsuario,
  StatusCadastro,
  UsuarioAdmin,
} from "./tipos";

interface ParametrosListarUsuarios {
  role?: RoleUsuario;
  statusCadastro?: StatusCadastro | "todos";
  busca?: string;
  limit?: number;
  offset?: number;
}

export function listarUsuarios(params: ParametrosListarUsuarios = {}): Promise<ListaUsuarios> {
  const query = new URLSearchParams();
  if (params.role) query.set("role", params.role);
  if (params.statusCadastro) query.set("status_cadastro", params.statusCadastro);
  if (params.busca) query.set("busca", params.busca);
  query.set("limit", String(params.limit ?? 20));
  query.set("offset", String(params.offset ?? 0));
  return get<ListaUsuarios>(`/api/usuarios?${query.toString()}`);
}

export function editarUsuario(
  usuarioId: number,
  campos: { role?: RoleUsuario; isActive?: boolean }
): Promise<UsuarioAdmin> {
  const corpo: Record<string, unknown> = {};
  if (campos.role !== undefined) corpo.role = campos.role;
  if (campos.isActive !== undefined) corpo.is_active = campos.isActive;
  return patch<UsuarioAdmin>(`/api/usuarios/${usuarioId}`, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  });
}

export function aprovarUsuario(usuarioId: number): Promise<ResultadoDecisaoCadastro> {
  return postJson<ResultadoDecisaoCadastro>(`/api/usuarios/${usuarioId}/aprovar`, {});
}

export function reprovarUsuario(usuarioId: number): Promise<ResultadoDecisaoCadastro> {
  return postJson<ResultadoDecisaoCadastro>(`/api/usuarios/${usuarioId}/reprovar`, {});
}

export function aprovarUsuariosLote(ids: number[]): Promise<ResultadoDecisaoCadastroLote> {
  return postJson<ResultadoDecisaoCadastroLote>("/api/usuarios/aprovar-lote", { ids });
}

export function reprovarUsuariosLote(ids: number[]): Promise<ResultadoDecisaoCadastroLote> {
  return postJson<ResultadoDecisaoCadastroLote>("/api/usuarios/reprovar-lote", { ids });
}
