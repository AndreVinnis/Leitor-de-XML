import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { obterNota } from "../../api/notas";
import type { ItemNotaDetalhe, StatusNota } from "../../api/tipos";
import { Card } from "../../componentes/Card";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { ErroApi } from "../../api/cliente";
import estilos from "./NotaFiscal.module.css";

// Mesmo mapeamento de NotasFiscais.tsx/Dashboard.tsx: "duplicado" cai no
// estado neutro do protótipo (rótulo "Duplicado").
const STATUS_PARA_BADGE: Record<StatusNota, StatusBadge> = {
  sucesso: "sucesso",
  pendente: "pendente",
  erro: "erro",
  duplicado: "neutro",
};

const formatadorMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function formatarCnpj(cnpj: string | null): string | null {
  if (!cnpj) return null;
  const digitos = cnpj.replace(/\D/g, "");
  if (digitos.length !== 14) return cnpj;
  return digitos.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

function formatarQuantidade(quantidade: string | null): string {
  // quantidade chega como string decimal (nunca float) -- Number() aqui só
  // descarta zeros à direita (ex.: "120.0000" -> 120) para exibição.
  return quantidade ? Number(quantidade).toLocaleString("pt-BR") : "-";
}

const COLUNAS_ITENS: ColunaTabela<ItemNotaDetalhe>[] = [
  { chave: "numero_item", titulo: "Nº", largura: "40px", renderizar: (item) => item.numero_item ?? "-" },
  { chave: "codigo_produto", titulo: "Código", largura: "130px", renderizar: (item) => item.codigo_produto ?? "-" },
  { chave: "descricao_original", titulo: "Descrição original", renderizar: (item) => item.descricao_original },
  {
    chave: "produto_canonico_nome",
    titulo: "Produto canônico",
    renderizar: (item) =>
      item.produto_canonico_nome ?? <span className={estilos.naoNormalizado}>— não normalizado</span>,
  },
  { chave: "ncm", titulo: "NCM", largura: "80px", renderizar: (item) => item.ncm ?? "-" },
  { chave: "cfop", titulo: "CFOP", largura: "60px", renderizar: (item) => item.cfop ?? "-" },
  { chave: "quantidade", titulo: "Qtd", largura: "60px", renderizar: (item) => formatarQuantidade(item.quantidade) },
  { chave: "unidade", titulo: "Un", largura: "50px", renderizar: (item) => item.unidade ?? "-" },
  {
    chave: "valor_unitario",
    titulo: "Vl. unit.",
    largura: "100px",
    renderizar: (item) => (item.valor_unitario ? formatadorMoeda.format(Number(item.valor_unitario)) : "-"),
  },
  {
    chave: "valor_total",
    titulo: "Vl. total",
    largura: "110px",
    renderizar: (item) => (item.valor_total ? formatadorMoeda.format(Number(item.valor_total)) : "-"),
  },
];

export function NotaFiscal() {
  const { casoId, notaId } = useParams<{ casoId: string; notaId: string }>();
  const notaIdNumero = Number(notaId);

  const nota = useQuery({
    queryKey: ["nota", notaIdNumero],
    queryFn: () => obterNota(notaIdNumero),
  });

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <Link to={casoId ? `/casos/${casoId}/notas` : "#"} className={estilos.linkVoltar}>
          ← Voltar para Notas Fiscais
        </Link>

        {nota.data && (
          <div className={estilos.tituloComBadges}>
            <h1 className={estilos.titulo}>Nota {nota.data.numero ?? notaId}</h1>
            <Badge status="neutro" rotulo={nota.data.tipo === "entrada" ? "Entrada" : "Saída"} />
            {nota.data.status && <Badge status={STATUS_PARA_BADGE[nota.data.status]} />}
          </div>
        )}
      </div>

      {nota.isLoading && <p>Carregando nota...</p>}

      {nota.isError && (
        <p className={estilos.mensagemErro}>
          {nota.error instanceof ErroApi && nota.error.status === 404
            ? "Nota não encontrada."
            : "Não foi possível carregar a nota."}
        </p>
      )}

      {nota.data && (
        <>
          <Card className={estilos.cardCabecalho}>
            <div className={estilos.colunasCabecalho}>
              <div className={estilos.colunaCabecalho}>
                <div className={estilos.campo}>
                  <span className={estilos.rotuloCampo}>Chave de acesso</span>
                  <span className={estilos.valorCampo}>{nota.data.chave_acesso}</span>
                </div>
                <div className={estilos.campo}>
                  <span className={estilos.rotuloCampo}>Emitente</span>
                  <span className={estilos.valorCampo}>
                    {nota.data.emitente_nome ?? "-"}
                    {nota.data.emitente_cnpj && ` — ${formatarCnpj(nota.data.emitente_cnpj)}`}
                  </span>
                </div>
                <div className={estilos.campo}>
                  <span className={estilos.rotuloCampo}>Destinatário</span>
                  <span className={estilos.valorCampo}>
                    {nota.data.destinatario_nome ?? "-"}
                    {nota.data.destinatario_cnpj && ` — ${formatarCnpj(nota.data.destinatario_cnpj)}`}
                  </span>
                </div>
              </div>

              <div className={estilos.colunaCabecalho}>
                <div className={estilos.campo}>
                  <span className={estilos.rotuloCampo}>Série</span>
                  <span className={estilos.valorCampo}>{nota.data.serie ?? "-"}</span>
                </div>
                <div className={estilos.campo}>
                  <span className={estilos.rotuloCampo}>Data de emissão</span>
                  <span className={estilos.valorCampo}>
                    {nota.data.data_emissao ? new Date(nota.data.data_emissao).toLocaleDateString("pt-BR") : "-"}
                  </span>
                </div>
                <div className={estilos.campo}>
                  <span className={estilos.rotuloCampo}>Arquivo de origem</span>
                  <span className={estilos.valorCampo}>{nota.data.arquivo_origem ?? "-"}</span>
                </div>
              </div>
            </div>

            <div className={estilos.blocoValorTotal}>
              <span className={estilos.rotuloCampo}>Valor total</span>
              <span className={estilos.valorTotal}>
                {nota.data.valor_total ? formatadorMoeda.format(Number(nota.data.valor_total)) : "-"}
              </span>
            </div>
          </Card>

          <Card>
            <h2 className={estilos.tituloSecao}>Itens da nota</h2>
            <Tabela
              colunas={COLUNAS_ITENS}
              linhas={nota.data.itens}
              chaveLinha={(item) => item.id}
              vazio="Nenhum item nesta nota."
            />
          </Card>
        </>
      )}
    </div>
  );
}
