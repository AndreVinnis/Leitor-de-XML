import type { InputHTMLAttributes } from "react";
import estilos from "./CampoTexto.module.css";

interface CampoTextoProps extends InputHTMLAttributes<HTMLInputElement> {
  rotulo: string;
  erro?: string;
}

export function CampoTexto({ rotulo, erro, id, name, className, ...props }: CampoTextoProps) {
  const campoId = id ?? name;
  return (
    <div className={estilos.grupo}>
      <label htmlFor={campoId} className={estilos.rotulo}>
        {rotulo}
      </label>
      <input id={campoId} name={name} className={[estilos.campo, className].filter(Boolean).join(" ")} {...props} />
      {erro && <span className={estilos.erro}>{erro}</span>}
    </div>
  );
}
