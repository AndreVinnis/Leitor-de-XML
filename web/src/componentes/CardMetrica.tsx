import { Link } from "react-router-dom";
import { Card } from "./Card";
import estilos from "./CardMetrica.module.css";

interface CardMetricaProps {
  rotulo: string;
  valor: number | string;
  cor?: "primaria" | "accent" | "erro";
  to?: string;
}

export function CardMetrica({ rotulo, valor, cor = "primaria", to }: CardMetricaProps) {
  return (
    <Card className={estilos.cardMetrica}>
      <span className={estilos.rotulo}>{rotulo}</span>
      <strong className={[estilos.valor, estilos[cor]].join(" ")}>{valor}</strong>
      {to && (
        <Link to={to} className={estilos.verDetalhes}>
          Ver detalhes →
        </Link>
      )}
    </Card>
  );
}
