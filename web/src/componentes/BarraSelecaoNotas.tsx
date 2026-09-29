import type { ReactNode } from "react";
import { LIMITE_DOWNLOAD_DANFE, type FormatoDownload } from "../api/notas";
import { Botao } from "./Botao";
import estilos from "./BarraSelecaoNotas.module.css";

interface BarraSelecaoNotasProps {
  selecionadas: number;
  /** Formato do download em andamento, ou null se nenhum. */
  baixando: FormatoDownload | null;
  onSelecionarTodas: () => void;
  onLimpar: () => void;
  onBaixar: (formato: FormatoDownload) => void;
  selecionandoTodas?: boolean;
  /** Texto de destaque à direita da barra (ex.: total de resultados). */
  resumo?: ReactNode;
}

/** Mensagem para as notas que ficaram fora do download, conforme o formato. */
export function mensagemAusentes(formato: FormatoDownload, ausentes: number): string {
  return formato === "xml"
    ? `${ausentes} XML(s) não foram encontrados no servidor e ficaram fora do arquivo.`
    : `${ausentes} nota(s) sem XML no servidor ou que não puderam ser convertidas em DANFE ficaram fora do arquivo.`;
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
  const semSelecao = selecionadas === 0;
  const acimaLimiteDanfe = selecionadas > LIMITE_DOWNLOAD_DANFE;

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
      <Botao onClick={() => onBaixar("xml")} disabled={semSelecao || baixando !== null}>
        {baixando === "xml" ? "Baixando..." : `Baixar XML (${selecionadas})`}
      </Botao>
      <Botao
        onClick={() => onBaixar("danfe")}
        disabled={semSelecao || acimaLimiteDanfe || baixando !== null}
      >
        {baixando === "danfe" ? "Gerando PDF..." : `Baixar DANFE (${selecionadas})`}
      </Botao>
      {acimaLimiteDanfe && (
        <span className={estilos.aviso}>DANFE: até {LIMITE_DOWNLOAD_DANFE} notas por vez.</span>
      )}
      {resumo && <span className={estilos.resumo}>{resumo}</span>}
    </div>
  );
}
