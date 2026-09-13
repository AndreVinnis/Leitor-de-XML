import { useState } from "react";
import { useParams } from "react-router-dom";
import { consultar } from "../../api/consulta";
import { ErroApi } from "../../api/cliente";
import type { ResultadoConsulta } from "../../api/tipos";
import { Badge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { Card } from "../../componentes/Card";
import { useToast } from "../../componentes/Toast";
import estilos from "./Consulta.module.css";

/** Todas as colunas cujo primeiro valor não-nulo é numérico são alinhadas à direita, como no protótipo. */
function colunaENumerica(linhas: unknown[][], indiceColuna: number): boolean {
  for (const linha of linhas) {
    const valor = linha[indiceColuna];
    if (valor !== null && valor !== undefined) return typeof valor === "number";
  }
  return false;
}

function formatarCelula(valor: unknown): string {
  if (valor === null || valor === undefined) return "-";
  return String(valor);
}

export function Consulta() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const { notificar } = useToast();

  const [pergunta, setPergunta] = useState("");
  const [consultando, setConsultando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoConsulta | null>(null);
  const [bloqueio, setBloqueio] = useState<string | null>(null);

  async function handleConsultar() {
    if (!pergunta.trim()) return;
    setConsultando(true);
    setBloqueio(null);
    try {
      const resposta = await consultar(pergunta.trim(), casoIdNumero);
      setResultado(resposta);
    } catch (excecao) {
      if (excecao instanceof ErroApi && excecao.status === 422) {
        setResultado(null);
        setBloqueio(excecao.message);
      } else {
        notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
      }
    } finally {
      setConsultando(false);
    }
  }

  const colunasNumericas = resultado
    ? resultado.colunas.map((_, indice) => colunaENumerica(resultado.linhas, indice))
    : [];

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Consulta</h1>
        <p className={estilos.subtitulo}>Pergunte em linguagem natural sobre as notas fiscais do caso selecionado.</p>
      </div>

      <div className={estilos.blocoPergunta}>
        <label className={estilos.rotuloPergunta} htmlFor="pergunta">
          Pergunta
        </label>
        <textarea
          id="pergunta"
          className={estilos.campoPergunta}
          placeholder="Ex.: quais produtos têm maior quantidade e valor total recebido nas notas de entrada do caso selecionado?"
          value={pergunta}
          onChange={(evento) => setPergunta(evento.target.value)}
          rows={3}
        />
        <div className={estilos.acaoConsultar}>
          <Botao onClick={handleConsultar} disabled={!pergunta.trim() || consultando}>
            {consultando ? "Consultando..." : "Consultar"}
          </Botao>
        </div>
      </div>

      {bloqueio && (
        <div className={estilos.blocoBloqueado}>
          <p className={estilos.rotuloStatus}>STATUS DA CONSULTA</p>
          <Badge status="erro" rotulo="Bloqueada" />
          <div className={estilos.caixaBloqueio}>
            <p className={estilos.bloqueioTitulo}>Consulta recusada: {bloqueio}</p>
          </div>
        </div>
      )}

      {resultado && resultado.linhas.length === 0 && (
        <div className={estilos.estadoVazio}>
          <p className={estilos.estadoVazioTitulo}>Nenhum resultado para essa pergunta</p>
          <p className={estilos.estadoVazioTexto}>
            Tente reformular a pergunta ou verifique se o produto aparece nas notas do caso selecionado.
          </p>
        </div>
      )}

      {resultado && resultado.linhas.length > 0 && (
        <Card>
          <div className={estilos.tabelaWrapper}>
            <table className={estilos.tabela}>
              <thead>
                <tr>
                  {resultado.colunas.map((coluna, indice) => (
                    <th key={coluna} className={colunasNumericas[indice] ? estilos.celulaNumerica : undefined}>
                      {coluna}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {resultado.linhas.map((linha, indiceLinha) => (
                  // eslint-disable-next-line react/no-array-index-key -- a API não devolve um id de linha
                  <tr key={indiceLinha}>
                    {linha.map((valor, indiceColuna) => (
                      <td
                        key={indiceColuna}
                        className={colunasNumericas[indiceColuna] ? estilos.celulaNumerica : undefined}
                      >
                        {formatarCelula(valor)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {resultado && (
        <p className={estilos.contagem}>
          {resultado.total_linhas} resultado(s) encontrado(s)
        </p>
      )}

      {resultado && (
        <details className={estilos.sqlDetalhes}>
          <summary className={estilos.sqlResumo}>SQL gerado</summary>
          <pre className={estilos.sqlCodigo}>{resultado.sql_gerado}</pre>
        </details>
      )}
    </div>
  );
}
