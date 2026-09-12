import * as ToastPrimitive from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import estilos from "./Toast.module.css";

type Variante = "sucesso" | "erro";

interface Notificacao {
  id: number;
  mensagem: string;
  variante: Variante;
}

interface ContextoToastValor {
  notificar: (mensagem: string, variante?: Variante) => void;
}

const ContextoToast = createContext<ContextoToastValor | null>(null);

/**
 * Substitui session_state["mensagens_revisao"] do Streamlit (guardado ali
 * porque st.rerun() descartaria st.success) -- aqui o feedback vive num
 * provider de verdade, então some sozinho depois de `duration`.
 */
export function ProvedorToast({ children }: { children: ReactNode }) {
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);

  const notificar = useCallback((mensagem: string, variante: Variante = "sucesso") => {
    const id = Date.now();
    setNotificacoes((atual) => [...atual, { id, mensagem, variante }]);
  }, []);

  function remover(id: number) {
    setNotificacoes((atual) => atual.filter((notificacao) => notificacao.id !== id));
  }

  return (
    <ContextoToast.Provider value={{ notificar }}>
      <ToastPrimitive.Provider swipeDirection="right">
        {children}
        {notificacoes.map((notificacao) => (
          <ToastPrimitive.Root
            key={notificacao.id}
            className={[estilos.toast, estilos[notificacao.variante]].join(" ")}
            duration={4000}
            onOpenChange={(aberto) => {
              if (!aberto) remover(notificacao.id);
            }}
          >
            <ToastPrimitive.Description>{notificacao.mensagem}</ToastPrimitive.Description>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className={estilos.viewport} />
      </ToastPrimitive.Provider>
    </ContextoToast.Provider>
  );
}

export function useToast(): ContextoToastValor {
  const contexto = useContext(ContextoToast);
  if (!contexto) throw new Error("useToast precisa estar dentro de <ProvedorToast>");
  return contexto;
}
