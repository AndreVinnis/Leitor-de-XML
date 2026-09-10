import { createContext, useContext, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { listarCasos } from "../api/casos";
import type { ClienteCaso } from "../api/tipos";

interface ContextoCasoValor {
  casos: ClienteCaso[];
  carregando: boolean;
}

const ContextoCaso = createContext<ContextoCasoValor | null>(null);

/**
 * Caso ativo é global no Streamlit (session_state["caso_atual_id"], via
 * selectbox na sidebar) e obrigatório para dashboard/normalização/consulta.
 * Aqui a lista de casos vira contexto compartilhado, e o caso ativo em si
 * vive na URL (/casos/:casoId/dashboard) para a tela ser linkável.
 */
export function ProvedorCasos({ children }: { children: ReactNode }) {
  const { data, isLoading } = useQuery({ queryKey: ["casos"], queryFn: listarCasos });
  return (
    <ContextoCaso.Provider value={{ casos: data ?? [], carregando: isLoading }}>{children}</ContextoCaso.Provider>
  );
}

export function useCasos(): ContextoCasoValor {
  const contexto = useContext(ContextoCaso);
  if (!contexto) throw new Error("useCasos precisa estar dentro de <ProvedorCasos>");
  return contexto;
}
