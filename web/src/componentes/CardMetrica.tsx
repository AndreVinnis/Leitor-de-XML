import { Card } from "./Card";
import estilos from "./CardMetrica.module.css";

interface CardMetricaProps {
  rotulo: string;
  valor: number | string;
  cor?: "primaria" | "accent" | "erro";
}

export function CardMetrica({ rotulo, valor, cor = "primaria" }: CardMetricaProps) {
  return (
    <Card className={estilos.cardMetrica}>
      <span className={estilos.rotulo}>{rotulo}</span>
      <strong className={[estilos.valor, estilos[cor]].join(" ")}>{valor}</strong>
    </Card>
  );
}
