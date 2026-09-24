import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { baixarNotas, listarIdsNotas, listarNotas } from "../../api/notas";
import { ErroApi } from "../../api/cliente";
import type { StatusNota, TipoNota } from "../../api/tipos";
import { Select } from "../../componentes/Select";
import { Card } from "../../componentes/Card";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { Paginacao } from "../../componentes/Paginacao";
import { BarraSelecaoNotas } from "../../componentes/BarraSelecaoNotas";
import { useToast } from "../../componentes/Toast";
import estilos from "./NotasFiscais.module.css";

const STATUS_PARA_BADGE: Record<StatusNota, StatusBadge> = {
  sucesso: "sucesso",
  pendente: "pendente",
  erro: "erro",
  duplicado: "neutro",
  evento: "evento",
};

const OPCOES_STATUS: { valor: StatusNota | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Todos os status" },
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "sucesso", rotulo: "Sucesso" },
  { valor: "erro", rotulo: "Erro" },
  { valor: "duplicado", rotulo: "Duplicado" },
];

const ABAS_TIPO: { valor: TipoNota | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Todas" },
  { valor: "entrada", rotulo: "Entrada" },
  { valor: "saida", rotulo: "Saída" },
];

const LIMITE_NOTAS = 20;

interface NotaLinha {
  id: number;
  numero: string | null;
  tipo: TipoNota | null;
  emitente_nome: string | null;
  destinatario_nome: string | null;
  data_emissao: string | null;
  valor_total: string | null;
  status: StatusNota | null;
}

const formatadorMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const COLUNAS_NOTAS: ColunaTabela<NotaLinha>[] = [
  { chave: "numero", titulo: "Nº nota", renderizar: (nota) => nota.numero ?? "-" },
  {
    chave: "tipo",
    titulo: "Tipo",
    renderizar: (nota) =>
      nota.tipo ? <Badge status="neutro" rotulo={nota.tipo === "entrada" ? "Entrada" : "Saída"} /> : "-",
  },
  { chave: "emitente_nome", titulo: "Emitente", renderizar: (nota) => nota.emitente_nome ?? "-" },
  { chave: "destinatario_nome", titulo: "Destinatário", renderizar: (nota) => nota.destinatario_nome ?? "-" },
  {
    chave: "data_emissao",
    titulo: "Data",
    renderizar: (nota) => (nota.data_emissao ? new Date(nota.data_emissao).toLocaleDateString("pt-BR") : "-"),
  },
  {
    chave: "valor_total",
    titulo: "Valor",
    renderizar: (nota) => (nota.valor_total ? formatadorMoeda.format(Number(nota.valor_total)) : "-"),
  },
  {
    chave: "status",
    titulo: "Status",
    renderizar: (nota) => (nota.status ? <Badge status={STATUS_PARA_BADGE[nota.status]} /> : "-"),
  },
];

export function NotasFiscais() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const navigate = useNavigate();
  const { notificar } = useToast();

  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [selecionandoTodas, setSelecionandoTodas] = useState(false);
  const [baixando, setBaixando] = useState(false);
  // Filtros e página vivem na URL (não em useState): ao abrir uma nota e voltar,
  // o histórico restaura a lista exatamente como estava. `replace` evita que
  // cada mudança de filtro vire uma entrada do histórico.
  const [params, setParams] = useSearchParams();
  const tipoFiltro = (params.get("tipo") ?? "") as TipoNota | "";
  const statusFiltro = (params.get("status") ?? "") as StatusNota | "";
  const dataInicio = params.get("data_inicio") ?? "";
  const dataFim = params.get("data_fim") ?? "";
  const busca = params.get("q") ?? "";
  const offset = Number(params.get("offset") ?? 0) || 0;
  const [buscaDigitada, setBuscaDigitada] = useState(busca);

  // Mudar um filtro volta para a primeira página, exceto se for só a página.
  function atualizarParametros(mudancas: Record<string, string>) {
    setParams(
      (atual) => {
        const proximo = new URLSearchParams(atual);
        Object.entries(mudancas).forEach(([chave, valor]) => {
          if (valor) proximo.set(chave, valor);
          else proximo.delete(chave);
        });
        if (!("offset" in mudancas)) proximo.delete("offset");
        return proximo;
      },
      { replace: true }
    );
  }

  const setOffset = (novoOffset: number) => atualizarParametros({ offset: String(novoOffset || "") });

  // Debounce simples: só entra na URL (e dispara request) 400ms depois
  // de parar de digitar, para não fazer uma chamada por tecla.
  useEffect(() => {
    if (buscaDigitada === busca) return;
    const temporizador = setTimeout(() => atualizarParametros({ q: buscaDigitada }), 400);
    return () => clearTimeout(temporizador);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- atualizarParametros só usa setParams
  }, [buscaDigitada]);

  // A seleção vale para o filtro em que foi feita: mudou o filtro, recomeça.
  useEffect(() => {
    setSelecionadas(new Set());
  }, [casoIdNumero, tipoFiltro, statusFiltro, dataInicio, dataFim, busca]);

  const notas = useQuery({
    queryKey: ["notas", casoIdNumero, tipoFiltro, statusFiltro, dataInicio, dataFim, busca, offset],
    queryFn: () =>
      listarNotas({
        clienteCasoId: casoIdNumero,
        tipo: tipoFiltro || undefined,
        status: statusFiltro || undefined,
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        q: busca || undefined,
        limit: LIMITE_NOTAS,
        offset,
      }),
  });

  const temFiltroAtivo = Boolean(tipoFiltro || statusFiltro || dataInicio || dataFim || busca || buscaDigitada);

  function handleLimparFiltros() {
    setBuscaDigitada("");
    setParams({}, { replace: true });
  }

  function handleMudarTipo(novoTipo: TipoNota | "") {
    atualizarParametros({ tipo: novoTipo });
  }

  function handleMudarStatus(novoStatus: StatusNota | "") {
    atualizarParametros({ status: novoStatus });
  }

  function alternarSelecao(id: number) {
    setSelecionadas((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(id)) proximo.delete(id);
      else proximo.add(id);
      return proximo;
    });
  }

  async function handleSelecionarTodas() {
    setSelecionandoTodas(true);
    try {
      const resposta = await listarIdsNotas({
        clienteCasoId: casoIdNumero,
        tipo: tipoFiltro || undefined,
        status: statusFiltro || undefined,
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        q: busca || undefined,
      });
      setSelecionadas(new Set(resposta.ids));
      if (resposta.limitado) {
        notificar(
          `O filtro tem ${resposta.total} notas. Foram selecionadas as ${resposta.ids.length} mais recentes (limite por download).`,
          "erro"
        );
      }
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSelecionandoTodas(false);
    }
  }

  async function handleBaixar() {
    setBaixando(true);
    try {
      const ausentes = await baixarNotas([...selecionadas]);
      if (ausentes > 0) notificar(`${ausentes} XML(s) não foram encontrados no servidor e ficaram fora do arquivo.`, "erro");
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setBaixando(false);
    }
  }

  const colunas: ColunaTabela<NotaLinha>[] = [
    {
      chave: "selecao",
      titulo: "",
      largura: "32px",
      renderizar: (nota) => (
        <input
          type="checkbox"
          checked={selecionadas.has(nota.id)}
          onChange={() => alternarSelecao(nota.id)}
          onClick={(evento) => evento.stopPropagation()}
          aria-label={`Selecionar nota ${nota.numero ?? nota.id}`}
        />
      ),
    },
    ...COLUNAS_NOTAS,
  ];

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Notas Fiscais</h1>
        <p className={estilos.subtitulo}>Todas as notas importadas do caso selecionado</p>
      </div>

      <div className={estilos.barraFiltros}>
        {ABAS_TIPO.map((aba) => (
          <button
            key={aba.valor}
            type="button"
            className={`${estilos.tab} ${tipoFiltro === aba.valor ? estilos.tabAtiva : ""}`}
            onClick={() => handleMudarTipo(aba.valor)}
          >
            {aba.rotulo}
          </button>
        ))}

        <Select valor={statusFiltro} opcoes={OPCOES_STATUS} onMudar={handleMudarStatus} rotuloAria="Filtrar por status" />

        <input
          type="date"
          className={estilos.campoData}
          aria-label="Data inicial"
          value={dataInicio}
          onChange={(evento) => atualizarParametros({ data_inicio: evento.target.value })}
        />
        <input
          type="date"
          className={estilos.campoData}
          aria-label="Data final"
          value={dataFim}
          onChange={(evento) => atualizarParametros({ data_fim: evento.target.value })}
        />

        {temFiltroAtivo && (
          <button type="button" className={`${estilos.tab} ${estilos.limparFiltros}`} onClick={handleLimparFiltros}>
            Limpar filtros
          </button>
        )}

        <div className={estilos.espacador} />

        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar por nº, chave ou emitente"
          value={buscaDigitada}
          onChange={(evento) => setBuscaDigitada(evento.target.value)}
        />
      </div>

      <Card>
        {notas.data && <p className={estilos.contagem}>{notas.data.total} nota(s) no total</p>}

        <BarraSelecaoNotas
          selecionadas={selecionadas.size}
          selecionandoTodas={selecionandoTodas}
          baixando={baixando}
          onSelecionarTodas={handleSelecionarTodas}
          onLimpar={() => setSelecionadas(new Set())}
          onBaixar={handleBaixar}
        />

        <Tabela
          colunas={colunas}
          linhas={notas.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhuma nota encontrada com esse filtro."
          onClicarLinha={(linha) =>
            navigate(`/casos/${casoIdNumero}/notas/${linha.id}`, { state: { filtrosNotas: params.toString() } })
          }
        />

        {notas.data && <Paginacao offset={offset} limite={LIMITE_NOTAS} total={notas.data.total} onMudar={setOffset} />}
      </Card>
    </div>
  );
}
