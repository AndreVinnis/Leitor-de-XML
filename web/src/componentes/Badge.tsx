import estilos from "./Badge.module.css";

export type StatusBadge = "sucesso" | "pendente" | "erro" | "neutro" | "info" | "evento";

const ROTULOS: Record<StatusBadge, string> = {
  sucesso: "Processada",
  pendente: "Pendente",
  erro: "Erro",
  neutro: "Duplicado",
  info: "Info",
  evento: "Evento",
};

export function Badge({ status, rotulo }: { status: StatusBadge; rotulo?: string }) {
  return <span className={[estilos.badge, estilos[status]].join(" ")}>{rotulo ?? ROTULOS[status]}</span>;
}
