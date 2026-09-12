import { useEffect, useRef, useState, type FormEvent } from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth/ContextoAuth";
import { useCasos } from "../casos/ContextoCaso";
import { criarCaso } from "../api/casos";
import { useToast } from "../componentes/Toast";
import { Botao } from "../componentes/Botao";
import { CampoTexto } from "../componentes/CampoTexto";
import { Modal } from "../componentes/Modal";
import { ErroApi } from "../api/cliente";
import estilos from "./LayoutApp.module.css";

// Itens de navegação previstos no protótipo (telas 07 e 08) que ainda não
// têm rota no React -- ficam visíveis para bater com o Figma, mas inertes
// até a fase correspondente da migração ser feita, em vez de linkar para
// uma página que não existe.
const ITENS_EM_CONSTRUCAO = ["Produtos", "Consulta", "Aprovação de Cadastros", "Configurações"];

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/);
  const primeira = partes[0]?.[0] ?? "";
  const ultima = partes.length > 1 ? partes[partes.length - 1][0] : "";
  return (primeira + ultima).toUpperCase();
}

/** Espelha _sidebar_autenticada() de frontend/streamlit_app.py, com o visual de TopBar + Sidebar do protótipo. */
export function LayoutApp() {
  const { usuario, sair } = useAuth();
  const { casos, carregando } = useCasos();
  const { casoId } = useParams<{ casoId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [seletorAberto, setSeletorAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const [modalNovoCasoAberto, setModalNovoCasoAberto] = useState(false);
  const [nomeNovoCaso, setNomeNovoCaso] = useState("");
  const [identificacaoNovoCaso, setIdentificacaoNovoCaso] = useState("");
  const [salvandoCaso, setSalvandoCaso] = useState(false);

  const seletorRef = useRef<HTMLDivElement>(null);

  const casoAtivo = casos.find((caso) => String(caso.id) === casoId);

  const casosFiltrados = casos.filter((caso) => {
    const alvo = `${caso.nome_cliente} ${caso.identificacao_caso ?? ""}`.toLowerCase();
    return alvo.includes(busca.trim().toLowerCase());
  });

  // Fecha o dropdown ao clicar fora dele -- mesmo padrão de qualquer menu
  // suspenso que não é um <select> nativo nem um Radix Popover.
  useEffect(() => {
    if (!seletorAberto) return;
    function aoClicarFora(evento: MouseEvent) {
      if (seletorRef.current && !seletorRef.current.contains(evento.target as Node)) {
        setSeletorAberto(false);
      }
    }
    document.addEventListener("mousedown", aoClicarFora);
    return () => document.removeEventListener("mousedown", aoClicarFora);
  }, [seletorAberto]);

  function selecionarCaso(id: number) {
    setSeletorAberto(false);
    setBusca("");
    navigate(`/casos/${id}/dashboard`);
  }

  function abrirModalNovoCaso() {
    setSeletorAberto(false);
    setNomeNovoCaso("");
    setIdentificacaoNovoCaso("");
    setModalNovoCasoAberto(true);
  }

  async function handleCriarCaso(evento: FormEvent) {
    evento.preventDefault();
    if (!nomeNovoCaso.trim()) return;
    setSalvandoCaso(true);
    try {
      const caso = await criarCaso(nomeNovoCaso.trim(), identificacaoNovoCaso.trim() || undefined);
      await queryClient.invalidateQueries({ queryKey: ["casos"] });
      setModalNovoCasoAberto(false);
      navigate(`/casos/${caso.id}/dashboard`);
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Não foi possível criar o caso.", "erro");
    } finally {
      setSalvandoCaso(false);
    }
  }

  function estaAtivo(sufixo: string): boolean {
    return location.pathname.endsWith(sufixo);
  }

  return (
    <div className={estilos.layout}>
      <header className={estilos.topbar}>
        <div className={estilos.logo}>
          <div className={estilos.logoCirculo} />
          <span className={estilos.logoTexto}>Leitor de XML</span>
        </div>

        <div className={estilos.grupoDireita}>
          <div className={estilos.seletorCaso} ref={seletorRef}>
            <button
              type="button"
              className={estilos.pilulaCaso}
              disabled={carregando}
              onClick={() => setSeletorAberto((atual) => !atual)}
            >
              <span className={estilos.pilulaTextos}>
                <span className={estilos.pilulaRotulo}>Cliente / caso</span>
                <span className={estilos.pilulaValor}>
                  {carregando
                    ? "Carregando..."
                    : casoAtivo
                      ? `${casoAtivo.nome_cliente}${casoAtivo.identificacao_caso ? ` · ${casoAtivo.identificacao_caso}` : ""}`
                      : "Selecione um caso"}
                </span>
              </span>
              <span className={estilos.pilulaSeta}>⌄</span>
            </button>

            {seletorAberto && (
              <div className={estilos.dropdownCaso}>
                <input
                  type="text"
                  className={estilos.buscaCaso}
                  placeholder="Buscar cliente ou caso..."
                  value={busca}
                  onChange={(evento) => setBusca(evento.target.value)}
                  autoFocus
                />
                {casosFiltrados.length === 0 ? (
                  <div className={estilos.dropdownVazio}>
                    <p className={estilos.dropdownVazioTitulo}>
                      {casos.length === 0 ? "Nenhum caso cadastrado" : "Nenhum caso encontrado"}
                    </p>
                    <p className={estilos.dropdownVazioTexto}>
                      {casos.length === 0
                        ? "Cadastre o primeiro caso para continuar."
                        : "Tente buscar por outro nome."}
                    </p>
                  </div>
                ) : (
                  casosFiltrados.map((caso) => {
                    const ativo = String(caso.id) === casoId;
                    return (
                      <button
                        key={caso.id}
                        type="button"
                        className={`${estilos.itemCaso} ${ativo ? estilos.itemCasoAtivo : ""}`}
                        onClick={() => selecionarCaso(caso.id)}
                      >
                        <span className={estilos.itemCasoTextos}>
                          <span className={estilos.itemCasoNome}>{caso.nome_cliente}</span>
                          {caso.identificacao_caso && (
                            <span className={estilos.itemCasoIdentificacao}>{caso.identificacao_caso}</span>
                          )}
                        </span>
                        {ativo && <span className={estilos.itemCasoCheck}>✓</span>}
                      </button>
                    );
                  })
                )}
                <div className={estilos.dropdownDivisor} />
                <button type="button" className={estilos.botaoNovoCaso} onClick={abrirModalNovoCaso}>
                  + Novo caso
                </button>
              </div>
            )}
          </div>

          <div className={estilos.blocoUsuario}>
            <span className={estilos.nomeUsuario}>{usuario?.nome}</span>
            <div className={estilos.avatar}>{usuario ? iniciais(usuario.nome) : ""}</div>
          </div>
        </div>
      </header>

      <div className={estilos.corpo}>
        <aside className={estilos.sidebar}>
          <nav className={estilos.nav}>
            <button
              type="button"
              className={`${estilos.navItem} ${estaAtivo("/dashboard") ? estilos.navItemAtivo : ""}`}
              onClick={() => casoId && navigate(`/casos/${casoId}/dashboard`)}
            >
              <span className={estilos.navBolha} />
              Dashboard
            </button>
            <button
              type="button"
              className={`${estilos.navItem} ${estaAtivo("/upload") ? estilos.navItemAtivo : ""}`}
              onClick={() => casoId && navigate(`/casos/${casoId}/upload`)}
            >
              <span className={estilos.navBolha} />
              Upload de XML
            </button>
            <button
              type="button"
              className={`${estilos.navItem} ${estaAtivo("/notas") ? estilos.navItemAtivo : ""}`}
              onClick={() => casoId && navigate(`/casos/${casoId}/notas`)}
            >
              <span className={estilos.navBolha} />
              Notas Fiscais
            </button>
            {ITENS_EM_CONSTRUCAO.map((rotulo) => (
              <span key={rotulo} className={estilos.navItem} title="Em construção nesta fase da migração">
                <span className={estilos.navBolha} />
                {rotulo}
              </span>
            ))}
          </nav>

          <button type="button" className={`${estilos.navItem} ${estilos.navSair}`} onClick={sair}>
            <span className={estilos.navBolha} />
            Sair
          </button>
        </aside>

        <main className={estilos.conteudo}>
          <Outlet />
        </main>
      </div>

      <Modal aberto={modalNovoCasoAberto} onFechar={() => setModalNovoCasoAberto(false)} titulo="Novo caso">
        <form onSubmit={handleCriarCaso} className={estilos.formNovoCaso}>
          <CampoTexto
            rotulo="Nome do cliente (obrigatório)"
            placeholder="Digite o nome do cliente"
            autoFocus
            value={nomeNovoCaso}
            onChange={(evento) => setNomeNovoCaso(evento.target.value)}
            required
          />
          <CampoTexto
            rotulo="Identificação do caso (opcional)"
            placeholder="Ex.: Proc. 1234"
            value={identificacaoNovoCaso}
            onChange={(evento) => setIdentificacaoNovoCaso(evento.target.value)}
          />
          <div className={estilos.acoesModalNovoCaso}>
            <Botao type="button" variante="secundario" onClick={() => setModalNovoCasoAberto(false)}>
              Cancelar
            </Botao>
            <Botao type="submit" disabled={salvandoCaso}>
              {salvandoCaso ? "Criando..." : "Criar caso"}
            </Botao>
          </div>
        </form>
      </Modal>
    </div>
  );
}
