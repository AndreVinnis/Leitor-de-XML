import type { ButtonHTMLAttributes } from "react";
import estilos from "./Botao.module.css";

interface BotaoProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: "primario" | "secundario";
}

export function Botao({ variante = "primario", className, ...props }: BotaoProps) {
  const classes = [estilos.botao, estilos[variante], className].filter(Boolean).join(" ");
  return <button className={classes} {...props} />;
}
