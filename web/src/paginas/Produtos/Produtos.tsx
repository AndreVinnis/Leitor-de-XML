import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmarSugestao,
  confirmarSugestoesLote,
  corrigirSugestao,
  dispararNormalizacao,
  editarCanonico,
  listarCanonicos,
  listarSugestoes,
  normalizacaoEmAndamento,
  rejeitarSugestao,
  rejeitarSugestoesLote,
  statusNormalizacao,
  transferirCanonico,
} from "../../api/produtos";
import { useCategoriasDoCaso } from "../../api/useCategoriasDoCaso";
import { ErroApi } from "../../api/cliente";
import type { ProdutoCanonico, ResultadoRevisao, StatusRevisao, SugestaoNormalizacao } from "../../api/tipos";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import { Modal } from "../../componentes/Modal";
import { Paginacao } from "../../componentes/Paginacao";
import { SeletorProdutoCanonico } from "../../componentes/SeletorProdutoCanonico/SeletorProdutoCanonico";
import { SeletorCategoria } from "../../componentes/SeletorCategoria";
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

// Estados do Celery em que a task não muda mais.
const ESTADOS_FINAIS = new Set(["SUCCESS", "FAILURE", "REVOKED"]);

// Consultas seguidas com a trava fora desta task (e status não final) até
// considerar a task morta. Uma só não basta: ao terminar, a task solta a
// trava um instante antes de o Celery gravar o resultado.
const CONSULTAS_ATE_TASK_PERDIDA = 3;

export function Produtos() {
  const [aba, setAba] = useState<Aba>("sugestoes");
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const queryClient = useQueryClient();
  const { notificar } = useToast();
  const [taskId, setTaskId] = useState<string | null>(null);

  // Tasks já encerradas nesta tela -- nunca readotadas (nem pelo
  // em-andamento, nem pelo 409), para não repetir o toast de conclusão.
  const tasksEncerradas = useRef(new Set<string>());
  const consultasSemTrava = useRef(0);

  const acompanhar = useCallback((id: string) => {
    if (tasksEncerradas.current.has(id)) return false;
    consultasSemTrava.current = 0;
    setTaskId(id);
    return true;
  }, []);

  // Retoma o acompanhamento de uma normalização já em andamento no caso
  // (página recarregada no meio, ou disparada em outra aba) -- sem isso o
  // botão voltaria a ficar habilitado com a task ainda rodando.
  const emAndamento = useQuery({
    queryKey: ["normalizacao-em-andamento", casoIdNumero],
    queryFn: () => normalizacaoEmAndamento(casoIdNumero),
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    const taskEmAndamento = emAndamento.data?.task_id;
    if (taskEmAndamento) acompanhar(taskEmAndamento);
  }, [emAndamento.data, acompanhar]);

  const normalizar = useMutation({
    mutationFn: () => dispararNormalizacao(casoIdNumero),
    onSuccess: (resposta) => {
      acompanhar(resposta.task_id);
      notificar("Normalização disparada em segundo plano.");
    },
    onError: async (erro) => {
      // 409: já existe normalização em andamento no caso (trava por caso no
      // backend) -- em vez de só mostrar o erro, passa a acompanhar aquela.
      if (erro instanceof ErroApi && erro.status === 409) {
        try {
          const { task_id: taskEmAndamento } = await normalizacaoEmAndamento(casoIdNumero);
          if (taskEmAndamento && acompanhar(taskEmAndamento)) {
            notificar("Já existe uma normalização em andamento para este caso. Acompanhando o progresso.");
            return;
          }
        } catch {
          /* cai na mensagem de erro abaixo */
        }
      }
      notificar(erro instanceof ErroApi ? erro.message : "Erro ao disparar normalização.", "erro");
    },
  });

  const statusTask = useQuery({
    queryKey: ["normalizacao-status", taskId],
    queryFn: () => statusNormalizacao(taskId as string, casoIdNumero),
    enabled: taskId !== null,
    // Reconsulta sozinho enquanto a task não terminar (mesmo padrão do
    // progresso de upload em UploadXml.tsx).
    refetchInterval: (query) => {
      const dados = query.state.data;
      if (!dados || !ESTADOS_FINAIS.has(dados.status)) return 1500;
      return false;
    },
  });

  // dataUpdatedAt nas dependências: consultas seguidas com a mesma resposta
  // mantêm a mesma referência de `data` (structural sharing), e a contagem
  // de consultas sem trava precisa avançar mesmo assim.
  useEffect(() => {
    const dados = statusTask.data;
    if (!dados || taskId === null || dados.task_id !== taskId) return;

    const resultado = dados.resultado;
    if (!ESTADOS_FINAIS.has(dados.status)) {
      consultasSemTrava.current = dados.ativa === false ? consultasSemTrava.current + 1 : 0;
      if (consultasSemTrava.current < CONSULTAS_ATE_TASK_PERDIDA) return;
      notificar(
        "A normalização parou sem concluir (o processamento foi interrompido no servidor). " +
          'Os lotes já processados foram salvos; clique em "Normalizar produtos pendentes" para continuar.',
        "erro"
      );
    } else if (resultado?.status === "falha_lote") {
      const salvos = resultado.lotes_salvos ?? 0;
      notificar(
        `Normalização interrompida no lote ${resultado.lote_com_falha} de ${resultado.total_lotes}: ` +
          `${resultado.motivo ?? "motivo desconhecido"}. ` +
          (salvos > 0
            ? `${salvos} lote(s) já foram salvos; clique em "Normalizar produtos pendentes" para continuar de onde parou.`
            : 'Nenhum lote foi salvo; clique em "Normalizar produtos pendentes" para tentar de novo.'),
        "erro"
      );
    } else if (dados.status !== "SUCCESS" || resultado?.status === "erro_inesperado" || resultado?.status === "ja_em_andamento") {
      notificar(`Falha na normalização: ${resultado?.motivo ?? "motivo desconhecido"}`, "erro");
    } else {
      const sugestoesCriadas = resultado?.sugestoes_criadas ?? 0;
      notificar(
        sugestoesCriadas > 0
          ? `Normalização concluída: ${sugestoesCriadas} sugestão(ões) criada(s) para revisão.`
          : "Normalização concluída: nenhum item pendente encontrado."
      );
    }

    // Invalida também nas falhas: os lotes anteriores já foram salvos.
    queryClient.invalidateQueries({ queryKey: ["sugestoes", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["canonicos-categorias", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["canonicos-busca", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoIdNumero] });
    // Sem isso, voltar a esta tela serviria do cache o task_id já terminado
    // e o toast de conclusão apareceria de novo.
    queryClient.removeQueries({ queryKey: ["normalizacao-em-andamento", casoIdNumero] });
    tasksEncerradas.current.add(taskId);
    setTaskId(null);
  }, [statusTask.data, statusTask.dataUpdatedAt, taskId, queryClient, casoIdNumero, notificar]);

  const normalizando =
    normalizar.isPending || (taskId !== null && !(statusTask.data && ESTADOS_FINAIS.has(statusTask.data.status)));
  const progresso = statusTask.data?.progresso;
  const rotuloNormalizando =
    progresso && progresso.total_lotes > 0
      ? `Normalizando lote ${Math.min(progresso.lotes_salvos + 1, progresso.total_lotes)} de ${progresso.total_lotes}...`
      : "Normalizando...";

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
          {normalizando ? rotuloNormalizando : "Normalizar produtos pendentes"}
        </Botao>
      </div>

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

      {normalizando && (
        <div className={estilos.avisoNormalizando} role="status">
          <span className={estilos.spinner} />
          <span>Normalizando itens, isso pode demorar um pouco...</span>
        </div>
      )}
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

  const categorias = useCategoriasDoCaso(casoIdNumero).data ?? [];

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
    await queryClient.invalidateQueries({ queryKey: ["canonicos-categorias", casoIdNumero] });
    await queryClient.invalidateQueries({ queryKey: ["canonicos-busca", casoIdNumero] });
    await queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoIdNumero] });
  }

  function removerDaSelecao(id: number) {
    setSelecionados((atual) => {
      if (!atual.has(id)) return atual;
      const novo = new Set(atual);
      novo.delete(id);
      return novo;
    });
  }

  /**
   * Se as `quantidade` linhas que saem da lista eram todas as desta página
   * (a última, com offset > 0), volta uma página: senão a tabela ficaria vazia,
   * além do total. Só vale quando o filtro de status faz a linha sair da lista.
   */
  function voltarPaginaSeEsvaziou(quantidade: number, novoStatus: StatusRevisao) {
    const saiuDaLista = statusFiltro !== "todos" && statusFiltro !== novoStatus;
    const naPagina = sugestoes.data?.itens.length ?? 0;
    if (saiuDaLista && offset > 0 && quantidade >= naPagina) {
      setOffset(Math.max(0, offset - LIMITE_SUGESTOES));
    }
  }

  async function confirmarUnitario(sugestaoId: number) {
    try {
      const resultado = await confirmarSugestao(sugestaoId);
      const [ok, mensagem] = traduzirResultadoUnitario(resultado, "Sugestão aprovada com sucesso.");
      notificar(mensagem, ok ? "sucesso" : "erro");
      removerDaSelecao(sugestaoId);
      if (ok) voltarPaginaSeEsvaziou(1, "confirmado");
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
      removerDaSelecao(sugestaoId);
      if (ok) voltarPaginaSeEsvaziou(1, "rejeitado");
      await invalidarSugestoes();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  async function executarLote(acao: "confirmar" | "rejeitar") {
    // Só ids ainda pendentes nesta página: a seleção pode ter ficado obsoleta.
    const pendentes = new Set(idsPendentesPagina);
    const ids = Array.from(selecionados).filter((id) => pendentes.has(id));
    if (ids.length === 0) {
      setSelecionados(new Set());
      return;
    }
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
      if (sucesso) voltarPaginaSeEsvaziou(sucesso, acao === "confirmar" ? "confirmado" : "rejeitado");
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
      renderizar: (sugestao) => (
        <>
          <span className={estilos.pilula}>{sugestao.nome_canonico}</span>
          {sugestao.nome_canonico_vinculado && sugestao.nome_canonico_vinculado !== sugestao.nome_canonico && (
            <div className={estilos.textoVinculado}>Vinculado: {sugestao.nome_canonico_vinculado}</div>
          )}
        </>
      ),
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
        if (sugestao.status !== "pendente") {
          return (
            <button
              type="button"
              className={estilos.acaoEscolher}
              title="Escolher outro produto canônico"
              onClick={() => setCorrigindo(sugestao)}
            >
              ✎ Escolher produto
            </button>
          );
        }
        return (
          <div className={estilos.acoes}>
            <button
              type="button"
              className={estilos.acaoSucesso}
              title="Aprovar sugestão"
              onClick={() => confirmarUnitario(sugestao.id)}
            >
              ✓
            </button>
            <button
              type="button"
              className={estilos.acaoErro}
              title="Rejeitar sugestão"
              onClick={() => rejeitarUnitario(sugestao.id)}
            >
              ✕
            </button>
            <button
              type="button"
              className={estilos.acaoNeutra}
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
          onFechar={() => setCorrigindo(null)}
          onSalvo={async () => {
            removerDaSelecao(corrigindo.id);
            voltarPaginaSeEsvaziou(1, "confirmado");
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
  onFechar: () => void;
  onSalvo: () => void;
}

function ModalCorrigirSugestao({ sugestao, casoId, onFechar, onSalvo }: ModalCorrigirSugestaoProps) {
  const { notificar } = useToast();

  // Só a sugestão pendente abre no sugerido pela IA. Nas demais (rejeitada ou
  // já aprovada/corrigida), abre no canônico vinculado ao item, se houver.
  const pendente = sugestao.status === "pendente";
  const idInicial = pendente ? sugestao.produto_canonico_sugerido_id : sugestao.produto_canonico_vinculado_id;
  const nomeInicial = pendente ? sugestao.nome_canonico : sugestao.nome_canonico_vinculado;

  async function handleConfirmar(produtoCanonicoId: number) {
    try {
      const resultado = await corrigirSugestao(sugestao.id, produtoCanonicoId);
      const [ok, mensagem] = traduzirResultadoUnitario(resultado, "Sugestão corrigida com sucesso.");
      notificar(mensagem, ok ? "sucesso" : "erro");
      if (ok) onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  return (
    <SeletorProdutoCanonico
      casoId={casoId}
      titulo="Escolher produto canônico"
      contexto={
        <>
          <div className={estilos.contextoCampo}>
            <span className={estilos.contextoRotulo}>PRODUTO ORIGINAL (NF-E)</span>
            <span>{sugestao.descricao_original}</span>
          </div>
          <div className={estilos.contextoCampo}>
            <span className={estilos.contextoRotulo}>SUGESTÃO DA IA</span>
            <span className={estilos.pilula}>{sugestao.nome_canonico}</span>
          </div>
          <div className={estilos.contextoCampo}>
            <span className={estilos.contextoRotulo}>STATUS</span>
            <Badge status={STATUS_PARA_BADGE[sugestao.status]} rotulo={STATUS_PARA_ROTULO[sugestao.status]} />
          </div>
          <div className={estilos.contextoCampo}>
            <span className={estilos.contextoRotulo}>FORNECEDOR</span>
            <span>{sugestao.fornecedor ?? "-"}</span>
          </div>
        </>
      }
      idDestacado={sugestao.produto_canonico_sugerido_id}
      idInicial={idInicial ?? undefined}
      nomeInicial={nomeInicial ?? undefined}
      rotuloConfirmar="Confirmar escolha"
      onConfirmar={handleConfirmar}
      onFechar={onFechar}
    />
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
  const [transferindo, setTransferindo] = useState<ProdutoCanonico | null>(null);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const categorias = useCategoriasDoCaso(casoIdNumero).data ?? [];

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
            title="Transferir para outro produto canônico"
            onClick={() => setTransferindo(canonico)}
          >
            ⇄
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
            await queryClient.invalidateQueries({ queryKey: ["canonicos-categorias", casoIdNumero] });
            await queryClient.invalidateQueries({ queryKey: ["canonicos-busca", casoIdNumero] });
            notificar("Produto canônico atualizado com sucesso.", "sucesso");
          }}
        />
      )}

      {transferindo && (
        <ModalTransferirCanonico
          origem={transferindo}
          casoId={casoIdNumero}
          onFechar={() => setTransferindo(null)}
          onTransferido={async (nomeDestino, itensMovidos) => {
            // A origem some da lista. Se ela era a única linha desta página
            // (a última), o offset ficaria além do total e a tabela
            // apareceria vazia com só "Página anterior" habilitado.
            const eraUnicaDaPagina = (canonicos.data?.itens.length ?? 0) === 1;
            setTransferindo(null);
            if (eraUnicaDaPagina && offset > 0) setOffset(Math.max(0, offset - LIMITE_CANONICOS));
            await queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoIdNumero] });
            await queryClient.invalidateQueries({ queryKey: ["canonicos-categorias", casoIdNumero] });
            await queryClient.invalidateQueries({ queryKey: ["canonicos-busca", casoIdNumero] });
            await queryClient.invalidateQueries({ queryKey: ["itens-vinculados"] });
            notificar(
              `Produto transferido para "${nomeDestino}": ${itensMovidos} ${
                itensMovidos === 1 ? "item movido" : "itens movidos"
              }.`,
              "sucesso"
            );
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

interface ModalTransferirCanonicoProps {
  origem: ProdutoCanonico;
  casoId: number;
  onFechar: () => void;
  onTransferido: (nomeDestino: string, itensMovidos: number) => void;
}

/**
 * Absorve o canônico da linha (origem) em outro do mesmo caso. Operação
 * irreversível -- por isso não há seleção inicial (escolha explícita) e o
 * botão de confirmar só habilita depois da escolha.
 */
function ModalTransferirCanonico({ origem, casoId, onFechar, onTransferido }: ModalTransferirCanonicoProps) {
  const { notificar } = useToast();

  async function handleConfirmar(destinoId: number) {
    try {
      const resultado = await transferirCanonico(origem.id, destinoId);
      onTransferido(resultado.nome_canonico, resultado.itens_movidos);
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  return (
    <SeletorProdutoCanonico
      casoId={casoId}
      titulo="Transferir produto canônico"
      contexto={
        <p className={estilos.avisoModal}>
          Os {origem.itens_vinculados_count}{" "}
          {origem.itens_vinculados_count === 1 ? "item vinculado" : "itens vinculados"} a &quot;
          {origem.nome_canonico}&quot; -- mais os itens de notas canceladas, que não entram nessa
          contagem -- passam a apontar para o produto escolhido, junto com as sugestões da IA que
          citavam esta origem. Em seguida, &quot;{origem.nome_canonico}&quot; é excluído. Esta ação
          não pode ser desfeita.
        </p>
      }
      idsExcluidos={[origem.id]}
      rotuloConfirmar="Transferir"
      onConfirmar={handleConfirmar}
      onFechar={onFechar}
    />
  );
}
