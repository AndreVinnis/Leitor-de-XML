import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listarItensVinculados, reatribuirItem } from "../../api/produtos";
import { ErroApi } from "../../api/cliente";
import type { ItemVinculado, TipoNota } from "../../api/tipos";
import { Badge } from "../../componentes/Badge";
import { Card } from "../../componentes/Card";
import { Paginacao } from "../../componentes/Paginacao";
import { SeletorProdutoCanonico } from "../../componentes/SeletorProdutoCanonico/SeletorProdutoCanonico";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { useToast } from "../../componentes/Toast";
import estilos from "./ItensVinculados.module.css";

const LIMITE_ITENS = 20;

const formatadorMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const ABAS_TIPO: { valor: TipoNota | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Todas" },
  { valor: "entrada", rotulo: "Entrada" },
  { valor: "saida", rotulo: "Saída" },
];

export function ItensVinculados() {
  const { casoId, produtoCanonicoId } = useParams<{ casoId: string; produtoCanonicoId: string }>();
  const casoIdNumero = Number(casoId);
  const produtoCanonicoIdNumero = Number(produtoCanonicoId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [tipoFiltro, setTipoFiltro] = useState<TipoNota | "">("");
  const [fornecedor, setFornecedor] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);
  const [reatribuindo, setReatribuindo] = useState<ItemVinculado | null>(null);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const itens = useQuery({
    queryKey: [
      "itens-vinculados",
      produtoCanonicoIdNumero,
      tipoFiltro,
      fornecedor,
      dataInicio,
      dataFim,
      busca,
      offset,
    ],
    queryFn: () =>
      listarItensVinculados({
        produtoCanonicoId: produtoCanonicoIdNumero,
        tipo: tipoFiltro || undefined,
        fornecedor: fornecedor || undefined,
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        busca: busca || undefined,
        limit: LIMITE_ITENS,
        offset,
      }),
    enabled: Number.isFinite(produtoCanonicoIdNumero),
  });

  function resetarPagina() {
    setOffset(0);
  }

  async function handleReatribuido() {
    setReatribuindo(null);
    notificar("Item reatribuído com sucesso.", "sucesso");
    await queryClient.invalidateQueries({ queryKey: ["itens-vinculados", produtoCanonicoIdNumero] });
    await queryClient.invalidateQueries({ queryKey: ["canonicos-categorias", casoIdNumero] });
    await queryClient.invalidateQueries({ queryKey: ["canonicos-busca", casoIdNumero] });
    await queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoIdNumero] });
  }

  const colunas: ColunaTabela<ItemVinculado>[] = [
    { chave: "nota_numero", titulo: "Nº Nota", renderizar: (item) => item.nota_numero ?? "-" },
    {
      chave: "tipo",
      titulo: "Tipo",
      renderizar: (item) => <Badge status="neutro" rotulo={item.tipo === "entrada" ? "Entrada" : "Saída"} />,
    },
    { chave: "fornecedor", titulo: "Fornecedor", renderizar: (item) => item.fornecedor ?? "-" },
    {
      chave: "data_emissao",
      titulo: "Data",
      renderizar: (item) => (item.data_emissao ? new Date(item.data_emissao).toLocaleDateString("pt-BR") : "-"),
    },
    { chave: "descricao_original", titulo: "Descrição Original", renderizar: (item) => item.descricao_original },
    { chave: "quantidade", titulo: "Qtd", renderizar: (item) => item.quantidade ?? "-" },
    { chave: "unidade", titulo: "Un", renderizar: (item) => item.unidade ?? "-" },
    {
      chave: "valor_unitario",
      titulo: "Vl. Unit.",
      renderizar: (item) => (item.valor_unitario ? formatadorMoeda.format(Number(item.valor_unitario)) : "-"),
    },
    {
      chave: "valor_total",
      titulo: "Vl. Total",
      renderizar: (item) => (item.valor_total ? formatadorMoeda.format(Number(item.valor_total)) : "-"),
    },
    {
      chave: "acoes",
      titulo: "Ações",
      renderizar: (item) => (
        <button
          type="button"
          className={estilos.acaoEditar}
          title="Alterar produto canônico deste item"
          onClick={() => setReatribuindo(item)}
        >
          ✎
        </button>
      ),
    },
  ];

  return (
    <div className={estilos.pagina}>
      <button
        type="button"
        className={estilos.linkVoltar}
        onClick={() => navigate(`/casos/${casoIdNumero}/produtos`)}
      >
        ← Voltar para Produtos Canônicos
      </button>

      {itens.data && (
        <div className={estilos.cabecalho}>
          <div className={estilos.tituloLinha}>
            <h1 className={estilos.titulo}>{itens.data.produto_canonico.nome_canonico}</h1>
            {itens.data.produto_canonico.categoria && (
              <span className={estilos.pilulaCategoria}>{itens.data.produto_canonico.categoria}</span>
            )}
          </div>
          <p className={estilos.subtitulo}>{itens.data.total} itens vinculados</p>
        </div>
      )}

      <div className={estilos.barraFiltros}>
        {ABAS_TIPO.map((aba) => (
          <button
            key={aba.valor}
            type="button"
            className={`${estilos.tab} ${tipoFiltro === aba.valor ? estilos.tabAtiva : ""}`}
            onClick={() => {
              setTipoFiltro(aba.valor);
              resetarPagina();
            }}
          >
            {aba.rotulo}
          </button>
        ))}

        <input
          type="text"
          className={estilos.campoFiltro}
          placeholder="Fornecedor"
          value={fornecedor}
          onChange={(evento) => {
            setFornecedor(evento.target.value);
            resetarPagina();
          }}
        />
        <input
          type="date"
          className={estilos.campoData}
          aria-label="De"
          value={dataInicio}
          onChange={(evento) => {
            setDataInicio(evento.target.value);
            resetarPagina();
          }}
        />
        <input
          type="date"
          className={estilos.campoData}
          aria-label="Até"
          value={dataFim}
          onChange={(evento) => {
            setDataFim(evento.target.value);
            resetarPagina();
          }}
        />
        <div className={estilos.espacador} />
        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar na descrição original..."
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            resetarPagina();
          }}
        />
      </div>

      <Card>
        <p className={estilos.tituloCard}>Itens vinculados</p>
        <Tabela
          colunas={colunas}
          linhas={itens.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhum item vinculado encontrado com esses filtros."
        />
        {itens.data && (
          <Paginacao offset={offset} limite={LIMITE_ITENS} total={itens.data.total} onMudar={setOffset} />
        )}
      </Card>

      {reatribuindo && (
        <ModalReatribuirItem
          item={reatribuindo}
          casoId={casoIdNumero}
          canonicoAtualId={Number(produtoCanonicoId)}
          onFechar={() => setReatribuindo(null)}
          onSalvo={handleReatribuido}
        />
      )}
    </div>
  );
}

interface ModalReatribuirItemProps {
  item: ItemVinculado;
  casoId: number;
  /** Canônico da página atual: o item já está nele, então não é opção de destino. */
  canonicoAtualId: number;
  onFechar: () => void;
  onSalvo: () => void;
}

const SEM_EXCLUIDOS: number[] = [];

function ModalReatribuirItem({ item, casoId, canonicoAtualId, onFechar, onSalvo }: ModalReatribuirItemProps) {
  const { notificar } = useToast();

  async function handleConfirmar(produtoCanonicoId: number) {
    try {
      await reatribuirItem(item.id, produtoCanonicoId);
      onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  return (
    <SeletorProdutoCanonico
      casoId={casoId}
      titulo="Alterar produto canônico do item"
      contexto={
        <p className={estilos.itemDescricao}>
          Item: <strong>{item.descricao_original}</strong>
        </p>
      }
      idsExcluidos={Number.isFinite(canonicoAtualId) ? [canonicoAtualId] : SEM_EXCLUIDOS}
      rotuloConfirmar="Salvar alterações"
      onConfirmar={handleConfirmar}
      onFechar={onFechar}
    />
  );
}
