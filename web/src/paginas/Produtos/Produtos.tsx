import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmarSugestao,
  confirmarSugestoesLote,
  corrigirSugestao,
  criarCanonico,
  dispararNormalizacao,
  editarCanonico,
  listarCanonicos,
  listarSugestoes,
  rejeitarSugestao,
  rejeitarSugestoesLote,
  statusNormalizacao,
} from "../../api/produtos";
import { ErroApi } from "../../api/cliente";
import type { ProdutoCanonico, ResultadoRevisao, StatusRevisao, SugestaoNormalizacao } from "../../api/tipos";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import { Modal } from "../../componentes/Modal";
import { Paginacao } from "../../componentes/Paginacao";
import { SeletorCategoria } from "../../componentes/SeletorCategoria";
import { Spinner } from "../../componentes/Spinner";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { useToast } from "../../componentes/Toast";
import estilos from "./Produtos.module.css";

type Aba = "sugestoes" | "canonicos";

const ABAS_STATUS: { valor: StatusRevisao | "todos"; rotulo: string }[] = [
  { valor: "todos", rotulo: "Todos" },
  { valor: "pendente", rotulo: "Pendentes" },
  { valor: "confirmado", rotulo: "Aprovados" },
  { valor: "rejeitado", rotulo: "Rejeitados" },
];

const STATUS_PARA_BADGE: Record<StatusRevisao, StatusBadge> = {
  pendente: "pendente",
  confirmado: "sucesso",
  rejeitado: "erro",
};

const STATUS_PARA_ROTULO: Record<StatusRevisao, string> = {
  pendente: "Pendente",
  confirmado: "Aprovado",
  rejeitado: "Rejeitado",
};

const LIMITE_SUGESTOES = 20;
const LIMITE_CANONICOS = 10;

export function Produtos() {
  const [aba, setAba] = useState<Aba>("sugestoes");
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const queryClient = useQueryClient();
  const { notificar } = useToast();
  const [taskId, setTaskId] = useState<string | null>(null);

  const normalizar = useMutation({
    mutationFn: () => dispararNormalizacao(casoIdNumero),
    onSuccess: (resposta) => {
      setTaskId(resposta.task_id);
      notificar("Normalização disparada em segundo plano.");
    },
    onError: (erro) => {
      notificar(erro instanceof ErroApi ? erro.message : "Erro ao disparar normalização.", "erro");
    },
  });

  const statusTask = useQuery({
    queryKey: ["normalizacao-status", taskId],
    queryFn: () => statusNormalizacao(taskId as string),
    enabled: taskId !== null,
    // Reconsulta sozinho enquanto a task não terminar (mesmo padrão do
    // progresso de upload em UploadXml.tsx).
    refetchInterval: (query) => {
      const dados = query.state.data;
      if (!dados || (dados.status !== "SUCCESS" && dados.status !== "FAILURE")) return 1500;
      return false;
    },
  });

  useEffect(() => {
    const dados = statusTask.data;
    if (!dados || (dados.status !== "SUCCESS" && dados.status !== "FAILURE")) return;

    if (dados.status === "FAILURE" || dados.resultado?.status === "erro_inesperado") {
      notificar(`Falha na normalização: ${dados.resultado?.motivo ?? "motivo desconhecido"}`, "erro");
    } else {
      const sugestoesCriadas = dados.resultado?.sugestoes_criadas ?? 0;
      notificar(
        sugestoesCriadas > 0
          ? `Normalização concluída: ${sugestoesCriadas} sugestão(ões) criada(s) para revisão.`
          : "Normalização concluída: nenhum item pendente encontrado."
      );
    }

    queryClient.invalidateQueries({ queryKey: ["sugestoes", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["canonicos-todos", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoIdNumero] });
    setTaskId(null);
  }, [statusTask.data, queryClient, casoIdNumero, notificar]);

  const normalizando = normalizar.isPending || (taskId !== null && statusTask.data?.status !== "SUCCESS" && statusTask.data?.status !== "FAILURE");

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <div className={estilos.cabecalhoTextos}>
          <h1 className={estilos.titulo}>Normalização de Produtos</h1>
          <p className={estilos.subtitulo}>
            Revise as sugestões geradas pela IA a partir das notas fiscais importadas
          </p>
        </div>
        <Botao onClick={() => normalizar.mutate()} disabled={normalizando}>
          {normalizando ? "Normalizando..." : "Normalizar produtos pendentes"}
        </Botao>
      </div>

      {normalizando && (
        <div className={estilos.avisoNormalizando}>
          <Spinner tamanho={16} />
          <span>Carregando, isso pode demorar um pouco.</span>
        </div>
      )}

      <div className={estilos.tabs}>
        <button
          type="button"
          className={`${estilos.tab} ${aba === "sugestoes" ? estilos.tabAtiva : ""}`}
          onClick={() => setAba("sugestoes")}
        >
          Sugestões da IA
        </button>
        <button
          type="button"
          className={`${estilos.tab} ${aba === "canonicos" ? estilos.tabAtiva : ""}`}
          onClick={() => setAba("canonicos")}
        >
          Produtos Canônicos
        </button>
      </div>

      {aba === "sugestoes" ? <AbaSugestoes /> : <AbaCanonicos />}
    </div>
  );
}

/** Toda ação de revisão devolve HTTP 200 mesmo em erro -- só o campo "status" do corpo diz o que houve. */
function traduzirResultadoUnitario(resultado: ResultadoRevisao, mensagemSucesso: string): [boolean, string] {
  if (resultado.status === "erro") {
    return [false, `Falha ao processar sugestão: ${resultado.motivo ?? "motivo desconhecido"}`];
  }
  return [true, mensagemSucesso];
}

function useCanonicosDoCaso(casoIdNumero: number) {
  return useQuery({
    queryKey: ["canonicos-todos", casoIdNumero],
    queryFn: () => listarCanonicos({ clienteCasoId: casoIdNumero, limit: 500 }),
    enabled: Number.isFinite(casoIdNumero),
  });
}

function AbaSugestoes() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [statusFiltro, setStatusFiltro] = useState<StatusRevisao | "todos">("pendente");
  const [categoriaFiltro, setCategoriaFiltro] = useState("");
  const [fornecedorFiltro, setFornecedorFiltro] = useState("");
  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [corrigindo, setCorrigindo] = useState<SugestaoNormalizacao | null>(null);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const canonicos = useCanonicosDoCaso(casoIdNumero);
  const categorias = useMemo(
    () => Array.from(new Set((canonicos.data?.itens ?? []).map((c) => c.categoria).filter(Boolean))) as string[],
    [canonicos.data]
  );

  const sugestoes = useQuery({
    queryKey: ["sugestoes", casoIdNumero, statusFiltro, categoriaFiltro, fornecedorFiltro, busca, offset],
    queryFn: () =>
      listarSugestoes({
        clienteCasoId: casoIdNumero,
        status: statusFiltro,
        categoria: categoriaFiltro || undefined,
        fornecedor: fornecedorFiltro || undefined,
        busca: busca || undefined,
        limit: LIMITE_SUGESTOES,
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

  const idsPendentesPagina = useMemo(
    () => (sugestoes.data?.itens ?? []).filter((s) => s.status === "pendente").map((s) => s.id),
    [sugestoes.data]
  );

  function selecionarTodos() {
    setSelecionados(new Set(idsPendentesPagina));
  }

  async function invalidarSugestoes() {
    await queryClient.invalidateQueries({ queryKey: ["sugestoes", casoIdNumero] });
    await queryClient.invalidateQueries({ queryKey: ["canonicos-todos", casoIdNumero] });
  }

  async function confirmarUnitario(sugestaoId: number) {
    try {
      const resultado = await confirmarSugestao(sugestaoId);
      const [ok, mensagem] = traduzirResultadoUnitario(resultado, "Sugestão aprovada com sucesso.");
      notificar(mensagem, ok ? "sucesso" : "erro");
      await invalidarSugestoes();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  async function rejeitarUnitario(sugestaoId: number) {
    try {
      const resultado = await rejeitarSugestao(sugestaoId);
      const [ok, mensagem] = traduzirResultadoUnitario(resultado, "Sugestão rejeitada com sucesso.");
      notificar(mensagem, ok ? "sucesso" : "erro");
      await invalidarSugestoes();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  async function executarLote(acao: "confirmar" | "rejeitar") {
    const ids = Array.from(selecionados);
    if (ids.length === 0) return;
    try {
      const resultado = await (acao === "confirmar" ? confirmarSugestoesLote(ids) : rejeitarSugestoesLote(ids));
      const falhas = resultado.resultados.filter((r) => r.status === "erro");
      const sucesso = resultado.resultados.length - falhas.length;
      if (sucesso) {
        notificar(
          `${sucesso} sugestão(ões) ${acao === "confirmar" ? "aprovada(s)" : "rejeitada(s)"} com sucesso.`,
          "sucesso"
        );
      }
      falhas.forEach((falha) =>
        notificar(`Sugestão ${falha.sugestao_id ?? "?"}: ${falha.motivo ?? "motivo desconhecido"}`, "erro")
      );
      setSelecionados(new Set());
      await invalidarSugestoes();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  const colunas: ColunaTabela<SugestaoNormalizacao>[] = [
    {
      chave: "selecao",
      titulo: "",
      largura: "32px",
      renderizar: (sugestao) => (
        <input
          type="checkbox"
          checked={selecionados.has(sugestao.id)}
          disabled={sugestao.status !== "pendente"}
          onChange={() => alternarSelecao(sugestao.id)}
          aria-label={`Selecionar sugestão ${sugestao.id}`}
        />
      ),
    },
    {
      chave: "descricao_original",
      titulo: "Produto Original (NF-e)",
      renderizar: (sugestao) => sugestao.descricao_original,
    },
    {
      chave: "nome_canonico",
      titulo: "Sugestão da IA",
      renderizar: (sugestao) => <span className={estilos.pilula}>{sugestao.nome_canonico}</span>,
    },
    {
      chave: "categoria",
      titulo: "Categoria",
      renderizar: (sugestao) =>
        sugestao.categoria ? <span className={estilos.pilulaCategoria}>{sugestao.categoria}</span> : "-",
    },
    {
      chave: "status",
      titulo: "Status",
      renderizar: (sugestao) => (
        <Badge status={STATUS_PARA_BADGE[sugestao.status]} rotulo={STATUS_PARA_ROTULO[sugestao.status]} />
      ),
    },
    {
      chave: "acoes",
      titulo: "Ações",
      renderizar: (sugestao) => {
        const jaRevisada = sugestao.status !== "pendente";
        return (
          <div className={estilos.acoes}>
            <button
              type="button"
              className={estilos.acaoSucesso}
              disabled={jaRevisada}
              title="Aprovar sugestão"
              onClick={() => confirmarUnitario(sugestao.id)}
            >
              ✓
            </button>
            <button
              type="button"
              className={estilos.acaoErro}
              disabled={jaRevisada}
              title="Rejeitar sugestão"
              onClick={() => rejeitarUnitario(sugestao.id)}
            >
              ✕
            </button>
            <button
              type="button"
              className={estilos.acaoNeutra}
              disabled={jaRevisada}
              title="Escolher outro produto canônico"
              onClick={() => setCorrigindo(sugestao)}
            >
              ✎
            </button>
          </div>
        );
      },
    },
  ];

  return (
    <>
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

        <select
          className={estilos.selectNativo}
          value={categoriaFiltro}
          onChange={(evento) => {
            setCategoriaFiltro(evento.target.value);
            resetarPagina();
          }}
          aria-label="Filtrar por categoria"
        >
          <option value="">Categoria</option>
          {categorias.map((categoria) => (
            <option key={categoria} value={categoria}>
              {categoria}
            </option>
          ))}
        </select>

        <input
          type="text"
          className={estilos.campoFiltro}
          placeholder="Fornecedor"
          value={fornecedorFiltro}
          onChange={(evento) => {
            setFornecedorFiltro(evento.target.value);
            resetarPagina();
          }}
        />

        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar produto..."
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            resetarPagina();
          }}
        />
      </div>

      <div className={estilos.barraLote}>
        <span className={estilos.contadorSelecionados}>{selecionados.size} selecionado(s)</span>
        <Botao
          variante="secundario"
          disabled={idsPendentesPagina.length === 0}
          onClick={selecionarTodos}
        >
          Selecionar todos
        </Botao>
        <Botao variante="secundario" disabled={selecionados.size === 0} onClick={() => executarLote("rejeitar")}>
          Rejeitar selecionados
        </Botao>
        <Botao disabled={selecionados.size === 0} onClick={() => executarLote("confirmar")}>
          Aprovar selecionados
        </Botao>
      </div>

      <Card>
        <Tabela
          colunas={colunas}
          linhas={sugestoes.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhuma sugestão encontrada com esses filtros."
        />
        {sugestoes.data && (
          <Paginacao offset={offset} limite={LIMITE_SUGESTOES} total={sugestoes.data.total} onMudar={setOffset} />
        )}
      </Card>

      {corrigindo && (
        <ModalCorrigirSugestao
          sugestao={corrigindo}
          casoId={casoIdNumero}
          canonicos={canonicos.data?.itens ?? []}
          categorias={categorias}
          onFechar={() => setCorrigindo(null)}
          onSalvo={async () => {
            setCorrigindo(null);
            await invalidarSugestoes();
          }}
        />
      )}
    </>
  );
}

interface ModalCorrigirSugestaoProps {
  sugestao: SugestaoNormalizacao;
  casoId: number;
  canonicos: ProdutoCanonico[];
  categorias: string[];
  onFechar: () => void;
  onSalvo: () => void;
}

function ModalCorrigirSugestao({
  sugestao,
  casoId,
  canonicos,
  categorias,
  onFechar,
  onSalvo,
}: ModalCorrigirSugestaoProps) {
  const { notificar } = useToast();
  const [escolha, setEscolha] = useState<string>(String(sugestao.produto_canonico_sugerido_id));
  const [nomeNovo, setNomeNovo] = useState("");
  const [categoriaNovo, setCategoriaNovo] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    try {
      let produtoCanonicoId: number;
      if (escolha === "novo") {
        if (!nomeNovo.trim()) {
          notificar("Informe o nome do novo produto canônico.", "erro");
          setSalvando(false);
          return;
        }
        const criado = await criarCanonico(casoId, nomeNovo.trim(), categoriaNovo.trim() || undefined);
        produtoCanonicoId = criado.id;
      } else {
        produtoCanonicoId = Number(escolha);
      }

      const resultado = await corrigirSugestao(sugestao.id, produtoCanonicoId);
      const [ok, mensagem] = traduzirResultadoUnitario(resultado, "Sugestão corrigida com sucesso.");
      notificar(mensagem, ok ? "sucesso" : "erro");
      if (ok) onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal aberto onFechar={onFechar} titulo="Corrigir sugestão">
      <form onSubmit={handleSubmit} className={estilos.formModal}>
        <div className={estilos.grupoCampo}>
          <label className={estilos.rotuloCampo}>Produto canônico</label>
          <select
            className={estilos.selectNativo}
            value={escolha}
            onChange={(evento) => setEscolha(evento.target.value)}
          >
            {canonicos.map((canonico) => (
              <option key={canonico.id} value={canonico.id}>
                {canonico.nome_canonico} ({canonico.categoria || "sem categoria"})
              </option>
            ))}
            <option value="novo">+ Criar novo</option>
          </select>
        </div>

        {escolha === "novo" && (
          <>
            <CampoTexto
              rotulo="Nome canônico"
              value={nomeNovo}
              onChange={(evento) => setNomeNovo(evento.target.value)}
              required
            />
            <SeletorCategoria
              rotulo="Categoria"
              valor={categoriaNovo}
              categoriasExistentes={categorias}
              onMudar={setCategoriaNovo}
            />
          </>
        )}

        <div className={estilos.acoesModal}>
          <Botao type="button" variante="secundario" onClick={onFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" disabled={salvando}>
            {salvando ? "Salvando..." : "Confirmar correção"}
          </Botao>
        </div>
      </form>
    </Modal>
  );
}

function AbaCanonicos() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [categoriaFiltro, setCategoriaFiltro] = useState("");
  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);
  const [editando, setEditando] = useState<ProdutoCanonico | null>(null);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const todosCanonicos = useCanonicosDoCaso(casoIdNumero);
  const categorias = useMemo(
    () =>
      Array.from(new Set((todosCanonicos.data?.itens ?? []).map((c) => c.categoria).filter(Boolean))) as string[],
    [todosCanonicos.data]
  );

  const canonicos = useQuery({
    queryKey: ["canonicos-tabela", casoIdNumero, categoriaFiltro, busca, offset],
    queryFn: () =>
      listarCanonicos({
        clienteCasoId: casoIdNumero,
        categoria: categoriaFiltro || undefined,
        busca: busca || undefined,
        limit: LIMITE_CANONICOS,
        offset,
      }),
  });

  const colunas: ColunaTabela<ProdutoCanonico>[] = [
    {
      chave: "nome_canonico",
      titulo: "Nome Canônico",
      renderizar: (canonico) => <span className={estilos.pilula}>{canonico.nome_canonico}</span>,
    },
    {
      chave: "categoria",
      titulo: "Categoria",
      renderizar: (canonico) =>
        canonico.categoria ? <span className={estilos.pilulaCategoria}>{canonico.categoria}</span> : "-",
    },
    {
      chave: "itens_vinculados_count",
      titulo: "Itens Vinculados",
      renderizar: (canonico) => `${canonico.itens_vinculados_count} ${canonico.itens_vinculados_count === 1 ? "item" : "itens"}`,
    },
    {
      chave: "acoes",
      titulo: "Ações",
      renderizar: (canonico) => (
        <div className={estilos.acoes}>
          <button
            type="button"
            className={estilos.acaoNeutra}
            title="Editar produto canônico"
            onClick={() => setEditando(canonico)}
          >
            ✎
          </button>
          <button
            type="button"
            className={estilos.acaoNeutra}
            title="Ver itens vinculados"
            onClick={() => navigate(`/casos/${casoIdNumero}/produtos/canonicos/${canonico.id}`)}
          >
            ☰
          </button>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className={estilos.barraFiltrosCanonicos}>
        <select
          className={estilos.selectNativo}
          value={categoriaFiltro}
          onChange={(evento) => {
            setCategoriaFiltro(evento.target.value);
            setOffset(0);
          }}
          aria-label="Filtrar por categoria"
        >
          <option value="">Categoria</option>
          {categorias.map((categoria) => (
            <option key={categoria} value={categoria}>
              {categoria}
            </option>
          ))}
        </select>

        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar produto canônico..."
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            setOffset(0);
          }}
        />
      </div>

      <Card>
        <Tabela
          colunas={colunas}
          linhas={canonicos.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhum produto canônico cadastrado neste caso ainda."
        />
        {canonicos.data && (
          <Paginacao offset={offset} limite={LIMITE_CANONICOS} total={canonicos.data.total} onMudar={setOffset} />
        )}
      </Card>

      {editando && (
        <ModalEditarCanonico
          canonico={editando}
          categorias={categorias}
          onFechar={() => setEditando(null)}
          onSalvo={async () => {
            setEditando(null);
            await queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoIdNumero] });
            await queryClient.invalidateQueries({ queryKey: ["canonicos-todos", casoIdNumero] });
            notificar("Produto canônico atualizado com sucesso.", "sucesso");
          }}
        />
      )}
    </>
  );
}

interface ModalEditarCanonicoProps {
  canonico: ProdutoCanonico;
  categorias: string[];
  onFechar: () => void;
  onSalvo: () => void;
}

function ModalEditarCanonico({ canonico, categorias, onFechar, onSalvo }: ModalEditarCanonicoProps) {
  const { notificar } = useToast();
  const [nome, setNome] = useState(canonico.nome_canonico);
  const [categoria, setCategoria] = useState(canonico.categoria ?? "");
  const [salvando, setSalvando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    try {
      await editarCanonico(canonico.id, { nomeCanonico: nome.trim(), categoria: categoria.trim() });
      onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal aberto onFechar={onFechar} titulo="Editar produto canônico">
      <form onSubmit={handleSubmit} className={estilos.formModal}>
        <CampoTexto
          rotulo="Nome canônico"
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          required
        />
        <SeletorCategoria rotulo="Categoria" valor={categoria} categoriasExistentes={categorias} onMudar={setCategoria} />
        <p className={estilos.avisoModal}>
          Alterar o nome ou a categoria afeta a exibição em todos os itens já vinculados a este produto.
        </p>
        <div className={estilos.acoesModal}>
          <Botao type="button" variante="secundario" onClick={onFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" disabled={salvando}>
            {salvando ? "Salvando..." : "Salvar alterações"}
          </Botao>
        </div>
      </form>
    </Modal>
  );
}
