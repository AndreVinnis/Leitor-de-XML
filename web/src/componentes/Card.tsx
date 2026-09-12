import type { ReactNode } from "react";
import estilos from "./Card.module.css";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={[estilos.card, className].filter(Boolean).join(" ")}>{children}</div>;
}
