import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { login as loginApi, logout as logoutApi, obterUsuarioLogado } from "../api/auth";
import { registrarCallbackSessaoExpirada } from "../api/cliente";
import type { UsuarioLogado } from "../api/tipos";

interface ContextoAuthValor {
  usuario: UsuarioLogado | null;
  carregando: boolean;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: () => Promise<void>;
  /** Atualiza o usuário armazenado (sessionStorage + contexto) após uma edição de perfil bem-sucedida. */
  atualizarUsuario: (usuario: UsuarioLogado) => void;
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
    // Sessão por cookie HttpOnly, deslizante (app/core/sessao_deslizante.py)
    // -- o servidor reemite o cookie sozinho enquanto o uso continuar, então
    // 401 só acontece se a sessão ficar de fato ociosa além da vida do
    // cookie, ou o servidor invalidar por outro motivo. Tratado num lugar só.
    registrarCallbackSessaoExpirada(() => setUsuario(null));
  }, []);

  async function entrar(email: string, senha: string) {
    setCarregando(true);
    try {
      // login() não devolve token -- a resposta é 204 e o cookie HttpOnly
      // de sessão vem no Set-Cookie, que o JS nunca lê.
      await loginApi(email, senha);
      const usuarioLogado = await obterUsuarioLogado();
      sessionStorage.setItem("usuario", JSON.stringify(usuarioLogado));
      setUsuario(usuarioLogado);
    } finally {
      setCarregando(false);
    }
  }

  async function sair() {
    try {
      await logoutApi();
    } catch {
      // Mesmo se a chamada falhar (rede, sessão já expirada), garante que o
      // estado local seja limpo -- não trava o usuário na tela.
    } finally {
      sessionStorage.removeItem("usuario");
      setUsuario(null);
    }
  }

  function atualizarUsuario(usuarioAtualizado: UsuarioLogado) {
    sessionStorage.setItem("usuario", JSON.stringify(usuarioAtualizado));
    setUsuario(usuarioAtualizado);
  }

  return (
    <ContextoAuth.Provider value={{ usuario, carregando, entrar, sair, atualizarUsuario }}>
      {children}
    </ContextoAuth.Provider>
  );
}

export function useAuth(): ContextoAuthValor {
  const contexto = useContext(ContextoAuth);
  if (!contexto) throw new Error("useAuth precisa estar dentro de <ProvedorAuth>");
  return contexto;
}
