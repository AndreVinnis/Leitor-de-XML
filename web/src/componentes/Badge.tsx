import estilos from "./Badge.module.css";

export type StatusBadge = "sucesso" | "pendente" | "erro" | "neutro" | "info";

const ROTULOS: Record<StatusBadge, string> = {
  sucesso: "Processada",
  pendente: "Pendente",
  erro: "Erro",
  neutro: "Duplicado",
  info: "Info",
};

export function Badge({ status, rotulo }: { status: StatusBadge; rotulo?: string }) {
  return <span className={[estilos.badge, estilos[status]].join(" ")}>{rotulo ?? ROTULOS[status]}</span>;
}
