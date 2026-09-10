import { useState, type FormEvent } from "react";
import { Outlet, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import * as SelectPrimitive from "@radix-ui/react-select";
import { useAuth } from "../auth/ContextoAuth";
import { useCasos } from "../casos/ContextoCaso";
import { criarCaso } from "../api/casos";
import { useToast } from "../componentes/Toast";
import { Botao } from "../componentes/Botao";
import { CampoTexto } from "../componentes/CampoTexto";
import { ErroApi } from "../api/cliente";
import estilos from "./LayoutApp.module.css";

// Itens de navegação previstos no protótipo (telas 05 a 08) que ainda não
// têm rota no React -- ficam visíveis para bater com o Figma, mas inertes
// até a fase correspondente da migração ser feita, em vez de linkar para
// uma página que não existe.
const ITENS_EM_CONSTRUCAO = ["Upload de XML", "Notas Fiscais", "Produtos", "Consulta", "Aprovação de Cadastros", "Configurações"];

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
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [criandoCaso, setCriandoCaso] = useState(false);
  const [nomeNovoCaso, setNomeNovoCaso] = useState("");
  const [salvandoCaso, setSalvandoCaso] = useState(false);

  const casoAtivo = casos.find((caso) => String(caso.id) === casoId);

  function selecionarCaso(id: string) {
    navigate(`/casos/${id}/dashboard`);
  }

  async function handleCriarCaso(evento: FormEvent) {
    evento.preventDefault();
    if (!nomeNovoCaso.trim()) return;
    setSalvandoCaso(true);
    try {
      const caso = await criarCaso(nomeNovoCaso.trim());
      await queryClient.invalidateQueries({ queryKey: ["casos"] });
      setNomeNovoCaso("");
      setCriandoCaso(false);
      navigate(`/casos/${caso.id}/dashboard`);
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Não foi possível criar o caso.", "erro");
    } finally {
      setSalvandoCaso(false);
    }
  }

  return (
    <div className={estilos.layout}>
      <header className={estilos.topbar}>
        <div className={estilos.logo}>
          <div className={estilos.logoCirculo} />
          <span className={estilos.logoTexto}>Leitor de XML</span>
        </div>

        <div className={estilos.grupoDireita}>
          <SelectPrimitive.Root
            value={casoId ?? ""}
            onValueChange={selecionarCaso}
            disabled={carregando || casos.length === 0}
          >
            <SelectPrimitive.Trigger className={estilos.pilulaCaso} aria-label="Cliente / caso ativo">
              <span className={estilos.pilulaTextos}>
                <span className={estilos.pilulaRotulo}>Cliente / caso</span>
                <span className={estilos.pilulaValor}>
                  <SelectPrimitive.Value placeholder={carregando ? "Carregando..." : "Selecione um caso"}>
                    {casoAtivo ? `${casoAtivo.nome_cliente}${casoAtivo.identificacao_caso ? ` · ${casoAtivo.identificacao_caso}` : ""}` : undefined}
                  </SelectPrimitive.Value>
                </span>
              </span>
              <SelectPrimitive.Icon className={estilos.pilulaSeta}>⌄</SelectPrimitive.Icon>
            </SelectPrimitive.Trigger>
            <SelectPrimitive.Portal>
              <SelectPrimitive.Content className={estilos.dropdownCaso}>
                <SelectPrimitive.Viewport>
                  {casos.map((caso) => (
                    <SelectPrimitive.Item key={caso.id} value={String(caso.id)} className={estilos.itemCaso}>
                      <SelectPrimitive.ItemText>
                        {caso.nome_cliente}
                        {caso.identificacao_caso ? ` · ${caso.identificacao_caso}` : ""}
                      </SelectPrimitive.ItemText>
                    </SelectPrimitive.Item>
                  ))}
                </SelectPrimitive.Viewport>
              </SelectPrimitive.Content>
            </SelectPrimitive.Portal>
          </SelectPrimitive.Root>

          <div className={estilos.acaoNovoCaso}>
            <button type="button" className={estilos.botaoNovoCaso} onClick={() => setCriandoCaso((atual) => !atual)}>
              + Novo caso
            </button>
            {criandoCaso && (
              <form onSubmit={handleCriarCaso} className={estilos.formNovoCaso}>
                <CampoTexto
                  rotulo="Nome do cliente"
                  autoFocus
                  value={nomeNovoCaso}
                  onChange={(evento) => setNomeNovoCaso(evento.target.value)}
                />
                <div className={estilos.acoesFormNovoCaso}>
                  <Botao type="submit" disabled={salvandoCaso}>
                    {salvandoCaso ? "Criando..." : "Criar"}
                  </Botao>
                  <Botao type="button" variante="secundario" onClick={() => setCriandoCaso(false)}>
                    Cancelar
                  </Botao>
                </div>
              </form>
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
              className={`${estilos.navItem} ${estilos.navItemAtivo}`}
              onClick={() => casoId && navigate(`/casos/${casoId}/dashboard`)}
            >
              <span className={estilos.navBolha} />
              Dashboard
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
    </div>
  );
}
