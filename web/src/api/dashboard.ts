import { get } from "./cliente";
import type { EstatisticasDashboard } from "./tipos";

export function obterEstatisticas(clienteCasoId: number): Promise<EstatisticasDashboard> {
  return get<EstatisticasDashboard>(`/api/dashboard/estatisticas?cliente_caso_id=${clienteCasoId}`);
}
