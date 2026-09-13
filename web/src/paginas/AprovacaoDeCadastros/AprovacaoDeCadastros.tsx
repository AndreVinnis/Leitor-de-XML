import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { aprovarUsuario, aprovarUsuariosLote, listarUsuarios, reprovarUsuario, reprovarUsuariosLote } from "../../api/usuarios";
import { ErroApi } from "../../api/cliente";
import type { StatusCadastro, UsuarioAdmin } from "../../api/tipos";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { Card } from "../../componentes/Card";
import { Modal } from "../../componentes/Modal";
import { Paginacao } from "../../componentes/Paginacao";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { useToast } from "../../componentes/Toast";
import estilos from "./AprovacaoDeCadastros.module.css";

const ABAS_STATUS: { valor: StatusCadastro | "todos"; rotulo: string }[] = [
  { valor: "pendente", rotulo: "Pendentes" },
  { valor: "aprovado", rotulo: "Aprovados" },
  { valor: "reprovado", rotulo: "Reprovados" },
  { valor: "todos", rotulo: "Todos" },
];

const STATUS_PARA_BADGE: Record<StatusCadastro, StatusBadge> = {
  pendente: "pendente",
  aprovado: "sucesso",
  reprovado: "erro",
};

const STATUS_PARA_ROTULO: Record<StatusCadastro, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  reprovado: "Reprovado",
};

const LIMITE = 20;

export function AprovacaoDeCadastros() {
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [statusFiltro, setStatusFiltro] = useState<StatusCadastro | "todos">("pendente");
  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [reprovando, setReprovando] = useState<UsuarioAdmin | null>(null);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const usuarios = useQuery({
    queryKey: ["cadastros", statusFiltro, busca, offset],
    queryFn: () =>
      listarUsuarios({
        statusCadastro: statusFiltro,
        busca: busca || undefined,
        limit: LIMITE,
        offset,
      }),
  });

  function resetarPagina() {
    setOffset(0);
    setSelecionados(new Set());
  }

  function alternarSelecao(id: number) {
    setSelecionados((atual) => {
      const novo = new Set(atual);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  async function invalidar() {
    await queryClient.invalidateQueries({ queryKey: ["cadastros"] });
  }

  async function aprovarUnitario(usuarioId: number) {
    try {
      const resultado = await aprovarUsuario(usuarioId);
      if (resultado.status === "erro") {
        notificar(`Falha ao aprovar cadastro: ${resultado.motivo ?? "motivo desconhecido"}`, "erro");
      } else {
        notificar("Cadastro aprovado com sucesso.", "sucesso");
      }
      await invalidar();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  async function confirmarReprovacao(usuarioId: number) {
    try {
      const resultado = await reprovarUsuario(usuarioId);
      if (resultado.status === "erro") {
        notificar(`Falha ao reprovar cadastro: ${resultado.motivo ?? "motivo desconhecido"}`, "erro");
      } else {
        notificar("Cadastro reprovado com sucesso.", "sucesso");
      }
      setReprovando(null);
      await invalidar();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  async function executarLote(acao: "aprovar" | "reprovar") {
    const ids = Array.from(selecionados);
    if (ids.length === 0) return;
    try {
      const resultado = await (acao === "aprovar" ? aprovarUsuariosLote(ids) : reprovarUsuariosLote(ids));
      const falhas = resultado.resultados.filter((r) => r.status === "erro");
      const sucesso = resultado.resultados.length - falhas.length;
      if (sucesso) {
        notificar(`${sucesso} cadastro(s) ${acao === "aprovar" ? "aprovado(s)" : "reprovado(s)"} com sucesso.`, "sucesso");
      }
      falhas.forEach((falha) => notificar(`Usuário ${falha.usuario_id ?? "?"}: ${falha.motivo ?? "motivo desconhecido"}`, "erro"));
      setSelecionados(new Set());
      await invalidar();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  const colunas: ColunaTabela<UsuarioAdmin>[] = [
    {
      chave: "selecao",
      titulo: "",
      largura: "32px",
      renderizar: (usuario) => (
        <input
          type="checkbox"
          checked={selecionados.has(usuario.id)}
          disabled={usuario.status_cadastro !== "pendente"}
          onChange={() => alternarSelecao(usuario.id)}
          aria-label={`Selecionar cadastro de ${usuario.nome}`}
        />
      ),
    },
    { chave: "nome", titulo: "Nome", renderizar: (u) => u.nome },
    { chave: "email", titulo: "E-mail", renderizar: (u) => u.email },
    {
      chave: "criado_em",
      titulo: "Solicitado em",
      renderizar: (u) => new Date(u.criado_em).toLocaleDateString("pt-BR"),
    },
    {
      chave: "status_cadastro",
      titulo: "Status",
      renderizar: (u) => <Badge status={STATUS_PARA_BADGE[u.status_cadastro]} rotulo={STATUS_PARA_ROTULO[u.status_cadastro]} />,
    },
    {
      chave: "acoes",
      titulo: "Ações",
      renderizar: (usuario) => {
        const jaDecidido = usuario.status_cadastro !== "pendente";
        return (
          <div className={estilos.acoes}>
            <button
              type="button"
              className={estilos.acaoSucesso}
              disabled={jaDecidido}
              title="Aprovar cadastro"
              onClick={() => aprovarUnitario(usuario.id)}
            >
              ✓
            </button>
            <button
              type="button"
              className={estilos.acaoErro}
              disabled={jaDecidido}
              title="Reprovar cadastro"
              onClick={() => setReprovando(usuario)}
            >
              ✕
            </button>
          </div>
        );
      },
    },
  ];

  const vazio =
    statusFiltro === "pendente"
      ? "Nenhum cadastro aguardando aprovação. Novas solicitações de acesso aparecem aqui."
      : "Nenhum cadastro encontrado com esses filtros.";

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Aprovação de Cadastros</h1>
        <p className={estilos.subtitulo}>Revise as solicitações de acesso ao sistema</p>
      </div>

      <div className={estilos.barraFiltros}>
        {ABAS_STATUS.map((item) => (
          <button
            key={item.valor}
            type="button"
            className={`${estilos.filtroStatus} ${statusFiltro === item.valor ? estilos.filtroStatusAtivo : ""}`}
            onClick={() => {
              setStatusFiltro(item.valor);
              resetarPagina();
            }}
          >
            {item.rotulo}
          </button>
        ))}

        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar por nome ou e-mail"
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            resetarPagina();
          }}
        />
      </div>

      <div className={estilos.barraLote}>
        <span className={estilos.contadorSelecionados}>{selecionados.size} selecionado(s)</span>
        <Botao variante="secundario" disabled={selecionados.size === 0} onClick={() => executarLote("reprovar")}>
          Reprovar selecionados
        </Botao>
        <Botao disabled={selecionados.size === 0} onClick={() => executarLote("aprovar")}>
          Aprovar selecionados
        </Botao>
      </div>

      <Card>
        <Tabela colunas={colunas} linhas={usuarios.data?.itens ?? []} chaveLinha={(linha) => linha.id} vazio={vazio} />
        {usuarios.data && <Paginacao offset={offset} limite={LIMITE} total={usuarios.data.total} onMudar={setOffset} />}
      </Card>

      {reprovando && (
        <Modal aberto onFechar={() => setReprovando(null)} titulo="Reprovar cadastro">
          <div className={estilos.formModal}>
            <p className={estilos.nomeUsuarioModal}>{reprovando.nome}</p>
            <p className={estilos.textoAjuda}>
              O usuário será notificado por e-mail e a decisão fica registrada no log de auditoria.
            </p>
            <div className={estilos.acoesModal}>
              <Botao type="button" variante="secundario" onClick={() => setReprovando(null)}>
                Cancelar
              </Botao>
              <Botao type="button" onClick={() => confirmarReprovacao(reprovando.id)}>
                Reprovar cadastro
              </Botao>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
