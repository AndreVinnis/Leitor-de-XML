import { Navigate, Outlet, useParams } from "react-router-dom";
import { useAuth } from "./ContextoAuth";

/**
 * Gate adicional sobre RotaProtegida (que já garante usuário logado): só
 * quem tem role="administrador" passa. Usado só na rota de Aprovação de
 * Cadastros -- o item nem aparece na sidebar para não-admins (LayoutApp),
 * mas a rota também precisa se proteger para quem digitar a URL direto.
 */
export function RotaAdmin() {
  const { usuario } = useAuth();
  const { casoId } = useParams<{ casoId: string }>();

  if (usuario?.role !== "administrador") {
    return <Navigate to={casoId ? `/casos/${casoId}/dashboard` : "/"} replace />;
  }
  return <Outlet />;
}
