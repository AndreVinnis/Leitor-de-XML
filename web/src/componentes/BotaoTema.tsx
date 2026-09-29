import { useTema } from "../tema/ContextoTema";
import estilos from "./BotaoTema.module.css";

/** Botão redondo da Top Bar (componente "Botão de Tema" do Figma): lua no tema claro, sol no escuro. */
export function BotaoTema() {
  const { tema, alternarTema } = useTema();
  const rotulo = tema === "escuro" ? "Ativar modo claro" : "Ativar modo escuro";

  return (
    <button type="button" className={estilos.botao} onClick={alternarTema} aria-label={rotulo} title={rotulo}>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {tema === "escuro" ? (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
          </>
        ) : (
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        )}
      </svg>
    </button>
  );
}
