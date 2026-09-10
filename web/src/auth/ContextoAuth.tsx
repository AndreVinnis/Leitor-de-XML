import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { login as loginApi, obterUsuarioLogado } from "../api/auth";
import { registrarCallbackSessaoExpirada } from "../api/cliente";
import type { UsuarioLogado } from "../api/tipos";

interface ContextoAuthValor {
  usuario: UsuarioLogado | null;
  carregando: boolean;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: () => void;
}

const ContextoAuth = createContext<ContextoAuthValor | null>(null);

function lerUsuarioArmazenado(): UsuarioLogado | null {
  try {
    const bruto = sessionStorage.getItem("usuario");
    return bruto ? (JSON.parse(bruto) as UsuarioLogado) : null;
  } catch {
    return null;
  }
}

export function ProvedorAuth({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<UsuarioLogado | null>(lerUsuarioArmazenado);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => {
    // O JWT dura 3600s (app/core/auth.py) e não há refresh token, então
    // expirar é o caminho normal, não uma excecão -- tratado num lugar só.
    registrarCallbackSessaoExpirada(() => setUsuario(null));
  }, []);

  async function entrar(email: string, senha: string) {
    setCarregando(true);
    try {
      const resposta = await loginApi(email, senha);
      sessionStorage.setItem("token", resposta.access_token);
      const usuarioLogado = await obterUsuarioLogado();
      sessionStorage.setItem("usuario", JSON.stringify(usuarioLogado));
      setUsuario(usuarioLogado);
    } finally {
      setCarregando(false);
    }
  }

  function sair() {
    // POST /api/auth/jwt/logout é um 204 no-op (JWT stateless não tem o
    // que revogar no servidor) -- sair é só limpar o lado do cliente.
    sessionStorage.removeItem("token");
    sessionStorage.removeItem("usuario");
    setUsuario(null);
  }

  return <ContextoAuth.Provider value={{ usuario, carregando, entrar, sair }}>{children}</ContextoAuth.Provider>;
}

export function useAuth(): ContextoAuthValor {
  const contexto = useContext(ContextoAuth);
  if (!contexto) throw new Error("useAuth precisa estar dentro de <ProvedorAuth>");
  return contexto;
}
