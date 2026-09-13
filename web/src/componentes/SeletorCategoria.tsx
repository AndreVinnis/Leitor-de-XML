import { useMemo, useState } from "react";
import estilos from "./SeletorCategoria.module.css";

interface SeletorCategoriaProps {
  rotulo: string;
  valor: string;
  categoriasExistentes: string[];
  onMudar: (valor: string) => void;
}

/**
 * Combobox de categoria: campo de texto livre (categoria não tem tabela
 * própria no backend, é string solta em ProdutoCanonico.categoria) com uma
 * lista suspensa de sugestão a partir das categorias já usadas no caso,
 * filtrada pelo que foi digitado -- espelha o componente "Categoria -
 * Combobox" do protótipo Figma (modal de editar produto canônico).
 */
export function SeletorCategoria({ rotulo, valor, categoriasExistentes, onMudar }: SeletorCategoriaProps) {
  const [aberto, setAberto] = useState(false);

  const sugestoes = useMemo(() => {
    const termo = valor.trim().toLowerCase();
    const unicas = Array.from(new Set(categoriasExistentes.filter(Boolean)));
    if (!termo) return unicas;
    return unicas.filter((categoria) => categoria.toLowerCase().includes(termo));
  }, [categoriasExistentes, valor]);

  return (
    <div className={estilos.grupo}>
      <label className={estilos.rotulo}>{rotulo}</label>
      <div className={estilos.wrapper}>
        <input
          type="text"
          className={estilos.campo}
          value={valor}
          onChange={(evento) => onMudar(evento.target.value)}
          onFocus={() => setAberto(true)}
          onBlur={() => setTimeout(() => setAberto(false), 150)}
        />
        {aberto && sugestoes.length > 0 && (
          <div className={estilos.dropdown}>
            {sugestoes.map((categoria) => (
              <button
                key={categoria}
                type="button"
                className={`${estilos.opcao} ${categoria === valor ? estilos.opcaoAtiva : ""}`}
                // onMouseDown (não onClick) dispara antes do onBlur do input,
                // senão o dropdown fecha antes do clique ser registrado.
                onMouseDown={(evento) => {
                  evento.preventDefault();
                  onMudar(categoria);
                  setAberto(false);
                }}
              >
                {categoria}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
