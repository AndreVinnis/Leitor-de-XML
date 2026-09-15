import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProvedorAuth } from "./auth/ContextoAuth";
import { RotaProtegida } from "./auth/RotaProtegida";
import { RotaAdmin } from "./auth/RotaAdmin";
import { ProvedorCasos, useCasos } from "./casos/ContextoCaso";
import { ProvedorToast } from "./componentes/Toast";
import { LayoutApp } from "./layout/LayoutApp";
import { Login } from "./paginas/Login/Login";
import { CriarConta } from "./paginas/CriarConta/CriarConta";
import { Dashboard } from "./paginas/Dashboard/Dashboard";
import { UploadXml } from "./paginas/UploadXml/UploadXml";
import { NotasFiscais } from "./paginas/NotasFiscais/NotasFiscais";
import { NotaFiscal } from "./paginas/NotaFiscal/NotaFiscal";
import { Produtos } from "./paginas/Produtos/Produtos";
import { ClientesCasos } from "./paginas/ClientesCasos/ClientesCasos";
import { ItensVinculados } from "./paginas/ItensVinculados/ItensVinculados";
import { Consulta } from "./paginas/Consulta/Consulta";
import { Configuracoes } from "./paginas/Configuracoes/Configuracoes";
import { AprovacaoDeCadastros } from "./paginas/AprovacaoDeCadastros/AprovacaoDeCadastros";
import { LogsAuditoria } from "./paginas/LogsAuditoria/LogsAuditoria";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

function ProvedorCasosLayout() {
  return (
    <ProvedorCasos>
      <Outlet />
    </ProvedorCasos>
  );
}

/**
 * Rota índice ("/") do app autenticado: manda para o dashboard do primeiro
 * caso, ou pede pra criar um caso se não houver nenhum ainda -- não existe
 * equivalente direto no Streamlit porque lá o caso ativo é só um estado em
 * memória, nunca uma rota.
 */
function RedirecionamentoInicial() {
  const { casos, carregando } = useCasos();
  if (carregando) return <p>Carregando casos...</p>;
  if (casos.length === 0) {
    return <p>Nenhum caso cadastrado ainda. Use "+ Novo caso" na barra lateral para começar.</p>;
  }
  return <Navigate to={`/casos/${casos[0].id}/dashboard`} replace />;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ProvedorToast>
        <ProvedorAuth>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/criar-conta" element={<CriarConta />} />
              <Route element={<RotaProtegida />}>
                <Route element={<ProvedorCasosLayout />}>
                  <Route element={<LayoutApp />}>
                    <Route index element={<RedirecionamentoInicial />} />
                    <Route path="casos/:casoId/dashboard" element={<Dashboard />} />
                    <Route path="casos/:casoId/upload" element={<UploadXml />} />
                    <Route path="casos/:casoId/notas" element={<NotasFiscais />} />
                    <Route path="casos/:casoId/notas/:notaId" element={<NotaFiscal />} />
                    <Route path="casos/:casoId/produtos" element={<Produtos />} />
                    <Route
                      path="casos/:casoId/produtos/canonicos/:produtoCanonicoId"
                      element={<ItensVinculados />}
                    />
                    <Route path="casos/:casoId/clientes-casos" element={<ClientesCasos />} />
                    <Route path="casos/:casoId/consulta" element={<Consulta />} />
                    <Route path="casos/:casoId/configuracoes" element={<Configuracoes />} />
                    <Route element={<RotaAdmin />}>
                      <Route path="casos/:casoId/aprovacao-de-cadastros" element={<AprovacaoDeCadastros />} />
                      <Route path="casos/:casoId/logs-auditoria" element={<LogsAuditoria />} />
                    </Route>
                  </Route>
                </Route>
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </ProvedorAuth>
      </ProvedorToast>
    </QueryClientProvider>
  );
}
