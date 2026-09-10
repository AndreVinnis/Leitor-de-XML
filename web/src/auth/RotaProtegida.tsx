import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./ContextoAuth";

/** Equivalente ao guard de streamlit_app.py: sem usuário, só /login. */
export function RotaProtegida() {
  const { usuario } = useAuth();
  if (!usuario) return <Navigate to="/login" replace />;
  return <Outlet />;
}
