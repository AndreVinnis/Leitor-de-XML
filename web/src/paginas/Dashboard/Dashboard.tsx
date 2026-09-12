import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { obterEstatisticas } from "../../api/dashboard";
import { listarNotas } from "../../api/notas";
import type { StatusNota } from "../../api/tipos";
import { CardMetrica } from "../../componentes/CardMetrica";
import { Card } from "../../componentes/Card";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import estilos from "./Dashboard.module.css";

// Mapeia o enum do backend para as variantes de badge do protótipo -- lá
// "duplicado" corresponde ao estado neutro (rótulo "Duplicado").
const STATUS_PARA_BADGE: Record<StatusNota, StatusBadge> = {
  sucesso: "sucesso",
  pendente: "pendente",
  erro: "erro",
  duplicado: "neutro",
};

const LIMITE_NOTAS_RECENTES = 5;

interface NotaLinha {
  id: number;
  numero: string | null;
  emitente_nome: string | null;
  data_emissao: string | null;
  valor_total: string | null;
  status: StatusNota | null;
}

const formatadorMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const COLUNAS_NOTAS: ColunaTabela<NotaLinha>[] = [
  { chave: "numero", titulo: "Número", renderizar: (nota) => nota.numero ?? "-" },
  { chave: "emitente_nome", titulo: "Emitente", renderizar: (nota) => nota.emitente_nome ?? "-" },
  {
    chave: "data_emissao",
    titulo: "Data de emissão",
    renderizar: (nota) => (nota.data_emissao ? new Date(nota.data_emissao).toLocaleDateString("pt-BR") : "-"),
  },
  {
    chave: "valor_total",
    titulo: "Valor total",
    // valor_total chega como string decimal (nunca float) -- só formata na
    // exibição, nunca antes.
    renderizar: (nota) => (nota.valor_total ? formatadorMoeda.format(Number(nota.valor_total)) : "-"),
  },
  {
    chave: "status",
    titulo: "Status",
    renderizar: (nota) => (nota.status ? <Badge status={STATUS_PARA_BADGE[nota.status]} /> : "-"),
  },
];

export function Dashboard() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const queryClient = useQueryClient();

  const estatisticas = useQuery({
    queryKey: ["dashboard-estatisticas", casoIdNumero],
    queryFn: () => obterEstatisticas(casoIdNumero),
  });

  const notas = useQuery({
    queryKey: ["notas-recentes", casoIdNumero],
    queryFn: () => listarNotas({ clienteCasoId: casoIdNumero, limit: LIMITE_NOTAS_RECENTES, offset: 0 }),
  });

  function handleAtualizarTudo() {
    queryClient.invalidateQueries({ queryKey: ["dashboard-estatisticas", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["notas-recentes", casoIdNumero] });
  }

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <div>
          <h1 className={estilos.titulo}>Dashboard</h1>
          <p className={estilos.subtitulo}>Visão geral das notas fiscais processadas</p>
        </div>
        <Botao variante="secundario" onClick={handleAtualizarTudo}>
          Atualizar
        </Botao>
      </div>

      <section className={estilos.cards}>
        <CardMetrica rotulo="Notas processadas" valor={estatisticas.data?.notas_processadas ?? "-"} cor="primaria" />
        <CardMetrica rotulo="Pendentes" valor={estatisticas.data?.pendentes ?? "-"} cor="accent" />
        <CardMetrica rotulo="Erros" valor={estatisticas.data?.erros ?? "-"} cor="erro" />
      </section>

      <Card>
        <div className={estilos.cabecalhoNotas}>
          <h2 className={estilos.tituloSecao}>Notas recentes</h2>
          <Link to={casoId ? `/casos/${casoId}/notas` : "#"} className={estilos.linkVerTodas}>
            Ver todas as notas →
          </Link>
        </div>

        <Tabela
          colunas={COLUNAS_NOTAS}
          linhas={notas.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhuma nota encontrada ainda. Envie XMLs na tela de Upload."
        />
      </Card>
    </div>
  );
}
