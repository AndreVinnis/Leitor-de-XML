import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listarNotas } from "../../api/notas";
import type { StatusNota, TipoNota } from "../../api/tipos";
import { Select } from "../../componentes/Select";
import { Card } from "../../componentes/Card";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { Paginacao } from "../../componentes/Paginacao";
import estilos from "./NotasFiscais.module.css";

const STATUS_PARA_BADGE: Record<StatusNota, StatusBadge> = {
  sucesso: "sucesso",
  pendente: "pendente",
  erro: "erro",
  duplicado: "neutro",
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

  const [tipoFiltro, setTipoFiltro] = useState<TipoNota | "">("");
  const [statusFiltro, setStatusFiltro] = useState<StatusNota | "">("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);

  // Debounce simples: só entra na queryKey (e dispara request) 400ms depois
  // de parar de digitar, para não fazer uma chamada por tecla.
  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

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

  function handleMudarTipo(novoTipo: TipoNota | "") {
    setTipoFiltro(novoTipo);
    setOffset(0);
  }

  function handleMudarStatus(novoStatus: StatusNota | "") {
    setStatusFiltro(novoStatus);
    setOffset(0);
  }

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
          onChange={(evento) => {
            setDataInicio(evento.target.value);
            setOffset(0);
          }}
        />
        <input
          type="date"
          className={estilos.campoData}
          aria-label="Data final"
          value={dataFim}
          onChange={(evento) => {
            setDataFim(evento.target.value);
            setOffset(0);
          }}
        />

        <div className={estilos.espacador} />

        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar por nº, chave ou emitente"
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            setOffset(0);
          }}
        />
      </div>

      <Card>
        {notas.data && <p className={estilos.contagem}>{notas.data.total} nota(s) no total</p>}

        <Tabela
          colunas={COLUNAS_NOTAS}
          linhas={notas.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhuma nota encontrada com esse filtro."
        />

        {notas.data && <Paginacao offset={offset} limite={LIMITE_NOTAS} total={notas.data.total} onMudar={setOffset} />}
      </Card>
    </div>
  );
}
