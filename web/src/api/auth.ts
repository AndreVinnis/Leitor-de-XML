import { get, patch, post, postJson } from "./cliente";
import type { UsuarioLogado } from "./tipos";

export function login(email: string, senha: string): Promise<void> {
  // POST /api/auth/cookie/login é OAuth2PasswordRequestForm: form-urlencoded,
  // com o e-mail no campo "username" -- não é JSON. Responde 204 sem corpo e
  // seta o cookie HttpOnly de sessão (app/core/auth.py::cookie_backend) --
  // não há token pra ler ou guardar aqui.
  const corpo = new URLSearchParams({ username: email, password: senha });
  return post<void>("/api/auth/cookie/login", {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: corpo,
  });
}

export function logout(): Promise<void> {
  return post<void>("/api/auth/cookie/logout");
}

export function obterUsuarioLogado(): Promise<UsuarioLogado> {
  return get<UsuarioLogado>("/api/auth/users/me");
}

export function criarConta(nome: string, email: string, senha: string): Promise<UsuarioLogado> {
  // POST /api/auth/register cria o usuário com is_active=False de cara
  // (UserManager.on_after_register em app/core/auth.py) -- fica pendente
  // até um administrador aprovar pelo link enviado por e-mail. Por isso
  // não faz sentido logar automaticamente depois desta chamada.
  return postJson<UsuarioLogado>("/api/auth/register", { email, password: senha, nome });
}

export function solicitarRedefinicaoSenha(email: string): Promise<void> {
  // Sempre responde 202 vazio, exista ou não o e-mail -- não revela se o
  // e-mail está cadastrado.
  return post<void>("/api/auth/forgot-password", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export function redefinirSenha(token: string, novaSenha: string): Promise<void> {
  return post<void>("/api/auth/reset-password", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password: novaSenha }),
  });
}

/**
 * PATCH /api/auth/users/me (fastapi-users) já existe e já aceita nome/email
 * do próprio usuário -- UsuarioUpdate (app/schemas/usuario.py) não expõe
 * role/status_cadastro, então não há risco de autopromoção por aqui.
 */
export function atualizarPerfil(campos: { nome?: string; email?: string }): Promise<UsuarioLogado> {
  return patch<UsuarioLogado>("/api/auth/users/me", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campos),
  });
}

/**
 * Mesma rota de atualizarPerfil, mudando só a senha. O fastapi-users não
 * exige a senha atual para isso -- quem chama (tela de Configurações) deve
 * validar a senha atual antes, chamando `login()` com ela, para não precisar
 * de um endpoint novo só para essa checagem. Sob cookie, isso reemite a
 * sessão do próprio usuário como efeito colateral (benigno).
 */
export function alterarSenha(novaSenha: string): Promise<UsuarioLogado> {
  return patch<UsuarioLogado>("/api/auth/users/me", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: novaSenha }),
  });
}
