import { get, post } from "./cliente";
import type { LoginResposta, UsuarioLogado } from "./tipos";

export function login(email: string, senha: string): Promise<LoginResposta> {
  // POST /api/auth/jwt/login é OAuth2PasswordRequestForm: form-urlencoded,
  // com o e-mail no campo "username" -- não é JSON.
  const corpo = new URLSearchParams({ username: email, password: senha });
  return post<LoginResposta>("/api/auth/jwt/login", {
    semAuth: true,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: corpo,
  });
}

export function obterUsuarioLogado(): Promise<UsuarioLogado> {
  return get<UsuarioLogado>("/api/auth/users/me");
}

export function solicitarRedefinicaoSenha(email: string): Promise<void> {
  // Sempre responde 202 vazio, exista ou não o e-mail -- não revela se o
  // e-mail está cadastrado.
  return post<void>("/api/auth/forgot-password", {
    semAuth: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}
