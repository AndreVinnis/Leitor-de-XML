import estilos from "./Spinner.module.css";

interface SpinnerProps {
  tamanho?: number;
}

export function Spinner({ tamanho = 16 }: SpinnerProps) {
  return (
    <span
      className={estilos.spinner}
      style={{ width: tamanho, height: tamanho }}
      role="status"
      aria-label="Carregando"
    />
  );
}
