import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Tema = "claro" | "escuro";

interface ContextoTemaValor {
  tema: Tema;
  alternarTema: () => void;
}

/** Mesma chave lida pelo script inline de index.html, que aplica o tema antes do React montar. */
const CHAVE_TEMA = "leitor-xml:tema";

const ContextoTema = createContext<ContextoTemaValor | null>(null);

function lerTemaArmazenado(): Tema {
  try {
    return localStorage.getItem(CHAVE_TEMA) === "escuro" ? "escuro" : "claro";
  } catch {
    return "claro";
  }
}

export function ProvedorTema({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(lerTemaArmazenado);

  useEffect(() => {
    document.documentElement.dataset.tema = tema;
    try {
      localStorage.setItem(CHAVE_TEMA, tema);
    } catch {
      // Armazenamento bloqueado (ex.: navegação privada): o tema vale só para esta aba.
    }
  }, [tema]);

  function alternarTema() {
    setTema((atual) => (atual === "escuro" ? "claro" : "escuro"));
  }

  return <ContextoTema.Provider value={{ tema, alternarTema }}>{children}</ContextoTema.Provider>;
}

export function useTema(): ContextoTemaValor {
  const contexto = useContext(ContextoTema);
  if (!contexto) throw new Error("useTema precisa estar dentro de <ProvedorTema>");
  return contexto;
}
