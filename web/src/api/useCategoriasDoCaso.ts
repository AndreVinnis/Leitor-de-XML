import { useQuery } from "@tanstack/react-query";
import { listarCategoriasCanonicos } from "./produtos";

/** Categorias distintas dos produtos canônicos do caso (alimenta filtros e o SeletorCategoria). */
export function useCategoriasDoCaso(casoId: number) {
  return useQuery({
    queryKey: ["canonicos-categorias", casoId],
    queryFn: () => listarCategoriasCanonicos(casoId),
    enabled: Number.isFinite(casoId),
  });
}
