import { Botao } from "./Botao";
import estilos from "./Paginacao.module.css";

interface PaginacaoProps {
  offset: number;
  limite: number;
  total: number;
  onMudar: (novoOffset: number) => void;
}

export function Paginacao({ offset, limite, total, onMudar }: PaginacaoProps) {
  const temAnterior = offset > 0;
  const temProxima = offset + limite < total;

  if (!temAnterior && !temProxima) return null;

  return (
    <div className={estilos.paginacao}>
      <Botao variante="secundario" disabled={!temAnterior} onClick={() => onMudar(Math.max(0, offset - limite))}>
        Página anterior
      </Botao>
      <Botao variante="secundario" disabled={!temProxima} onClick={() => onMudar(offset + limite)}>
        Próxima página
      </Botao>
    </div>
  );
}
