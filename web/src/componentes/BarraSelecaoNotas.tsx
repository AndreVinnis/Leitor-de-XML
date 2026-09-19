import type { ReactNode } from "react";
import { Botao } from "./Botao";
import estilos from "./BarraSelecaoNotas.module.css";

interface BarraSelecaoNotasProps {
  selecionadas: number;
  baixando: boolean;
  onSelecionarTodas: () => void;
  onLimpar: () => void;
  onBaixar: () => void;
  selecionandoTodas?: boolean;
  /** Texto de destaque � direita da barra (ex.: total de resultados). */
  resumo?: ReactNode;
}

/** Ações de seleção e download de notas, compartilhadas por Notas Fiscais e Consulta. */
export function BarraSelecaoNotas({
  selecionadas,
  baixando,
  onSelecionarTodas,
  onLimpar,
  onBaixar,
  selecionandoTodas = false,
  resumo,
}: BarraSelecaoNotasProps) {
  return (
    <div className={estilos.barra}>
      {selecionadas > 0 ? (
        <Botao variante="secundario" onClick={onLimpar}>
          Limpar seleção
        </Botao>
      ) : (
        <Botao variante="secundario" onClick={onSelecionarTodas} disabled={selecionandoTodas}>
          {selecionandoTodas ? "Selecionando..." : "Selecionar todas"}
        </Botao>
      )}
      <Botao onClick={onBaixar} disabled={selecionadas === 0 || baixando}>
        {baixando ? "Baixando..." : `Baixar selecionadas (${selecionadas})`}
      </Botao>
      {resumo && <span className={estilos.resumo}>{resumo}</span>}
    </div>
  );
}
