import type { ReactNode } from "react";
import estilos from "./Tabela.module.css";

export interface ColunaTabela<T> {
  chave: string;
  titulo: string;
  renderizar: (linha: T) => ReactNode;
}

interface TabelaProps<T> {
  colunas: ColunaTabela<T>[];
  linhas: T[];
  chaveLinha: (linha: T) => string | number;
  vazio?: ReactNode;
}

export function Tabela<T>({ colunas, linhas, chaveLinha, vazio }: TabelaProps<T>) {
  if (linhas.length === 0) {
    return <p className={estilos.vazio}>{vazio ?? "Nenhum registro encontrado."}</p>;
  }

  return (
    <div className={estilos.wrapper}>
      <table className={estilos.tabela}>
        <thead>
          <tr>
            {colunas.map((coluna) => (
              <th key={coluna.chave}>{coluna.titulo}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha) => (
            <tr key={chaveLinha(linha)}>
              {colunas.map((coluna) => (
                <td key={coluna.chave}>{coluna.renderizar(linha)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
