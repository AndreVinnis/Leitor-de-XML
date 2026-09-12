import { get, post, postJson } from "./cliente";
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

export function criarConta(nome: string, email: string, senha: string): Promise<UsuarioLogado> {
  // POST /api/auth/register cria o usuário com is_active=False de cara
  // (UserManager.on_after_register em app/core/auth.py) -- fica pendente
  // até um administrador aprovar pelo link enviado por e-mail. Por isso
  // não faz sentido logar automaticamente depois desta chamada.
  return postJson<UsuarioLogado>("/api/auth/register", { email, password: senha, nome }, { semAuth: true });
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
