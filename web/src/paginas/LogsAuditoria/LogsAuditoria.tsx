import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listarLogsAuditoria } from "../../api/auditoria";
import type { LogAuditoria } from "../../api/tipos";
import { Botao } from "../../componentes/Botao";
import { Card } from "../../componentes/Card";
import { Modal } from "../../componentes/Modal";
import { Paginacao } from "../../componentes/Paginacao";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import estilos from "./LogsAuditoria.module.css";

const LIMITE = 20;

export function LogsAuditoria() {
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [offset, setOffset] = useState(0);
  const [selecionado, setSelecionado] = useState<LogAuditoria | null>(null);

  const logs = useQuery({
    queryKey: ["logs-auditoria", dataInicio, dataFim, offset],
    queryFn: () =>
      listarLogsAuditoria({
        dataInicio: dataInicio || undefined,
        dataFim: dataFim || undefined,
        limit: LIMITE,
        offset,
      }),
  });

  const colunas: ColunaTabela<LogAuditoria>[] = [
    {
      chave: "criado_em",
      titulo: "Data/Hora",
      renderizar: (log) => new Date(log.criado_em).toLocaleString("pt-BR"),
    },
    { chave: "usuario_nome", titulo: "Usuário", renderizar: (log) => log.usuario_nome },
    { chave: "acao", titulo: "Ação", renderizar: (log) => log.acao },
    {
      chave: "resumo",
      titulo: "Resumo",
      renderizar: (log) => <span className={estilos.resumo}>{log.resumo ?? "-"}</span>,
    },
    {
      chave: "acoes",
      titulo: "",
      renderizar: (log) => (
        <button type="button" className={estilos.verDetalhes} onClick={() => setSelecionado(log)}>
          Ver detalhes
        </button>
      ),
    },
  ];

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Logs de Auditoria</h1>
        <p className={estilos.subtitulo}>Histórico de ações realizadas no sistema, da mais recente para a mais antiga</p>
      </div>

      <div className={estilos.barraFiltros}>
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
      </div>

      <Card>
        <Tabela
          colunas={colunas}
          linhas={logs.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhum log encontrado para o período selecionado."
        />
        {logs.data && <Paginacao offset={offset} limite={LIMITE} total={logs.data.total} onMudar={setOffset} />}
      </Card>

      {selecionado && (
        <Modal aberto onFechar={() => setSelecionado(null)} titulo="Detalhes do log">
          <div className={estilos.detalheModal}>
            <div>
              <p className={estilos.rotuloDetalhe}>Ação</p>
              <p className={estilos.valorDetalhe}>{selecionado.acao}</p>
            </div>
            <div>
              <p className={estilos.rotuloDetalhe}>Pergunta do usuário</p>
              <p className={estilos.valorDetalhe}>{selecionado.pergunta_usuario ?? "—"}</p>
            </div>
            <div>
              <p className={estilos.rotuloDetalhe}>Resultado</p>
              <p className={estilos.valorDetalhe}>{selecionado.resumo ?? "—"}</p>
            </div>
            <div>
              <p className={estilos.rotuloDetalhe}>SQL gerado</p>
              <p className={estilos.valorDetalheCodigo}>{selecionado.sql_gerado ?? "—"}</p>
            </div>
            <div className={estilos.acoesModal}>
              <Botao type="button" variante="secundario" onClick={() => setSelecionado(null)}>
                Fechar
              </Botao>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
