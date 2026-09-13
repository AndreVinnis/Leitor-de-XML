import { postJson } from "./cliente";
import type { ResultadoConsulta } from "./tipos";

/**
 * POST /api/consulta (sem barra final -- ver nota 2 do topo de cliente.ts).
 * Quando o SQL gerado pela IA reprova na validação de segurança
 * (app/core/sql_seguranca.py), a rota devolve 422 e isso chega aqui como
 * ErroApi com status 422 -- a página distingue esse caso (consulta
 * bloqueada) de uma falha de comunicação genérica pelo `status`.
 */
export function consultar(pergunta: string, clienteCasoId: number): Promise<ResultadoConsulta> {
  return postJson<ResultadoConsulta>("/api/consulta", {
    pergunta,
    cliente_caso_id: clienteCasoId,
  });
}
