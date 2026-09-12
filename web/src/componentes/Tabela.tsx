import type { ReactNode } from "react";
import estilos from "./Tabela.module.css";

export interface ColunaTabela<T> {
  chave: string;
  titulo: string;
  renderizar: (linha: T) => ReactNode;
  largura?: string;
}

interface TabelaProps<T> {
  colunas: ColunaTabela<T>[];
  linhas: T[];
  chaveLinha: (linha: T) => string | number;
  vazio?: ReactNode;
  onClicarLinha?: (linha: T) => void;
}

export function Tabela<T>({ colunas, linhas, chaveLinha, vazio, onClicarLinha }: TabelaProps<T>) {
  if (linhas.length === 0) {
    return <p className={estilos.vazio}>{vazio ?? "Nenhum registro encontrado."}</p>;
  }

  return (
    <div className={estilos.wrapper}>
      <table className={estilos.tabela}>
        <thead>
          <tr>
            {colunas.map((coluna) => (
              <th key={coluna.chave} style={{ width: coluna.largura }}>
                {coluna.titulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha) => (
            <tr
              key={chaveLinha(linha)}
              className={onClicarLinha ? estilos.linhaClicavel : undefined}
              onClick={onClicarLinha ? () => onClicarLinha(linha) : undefined}
            >
              {colunas.map((coluna) => (
                <td key={coluna.chave} style={{ width: coluna.largura }}>
                  {coluna.renderizar(linha)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
