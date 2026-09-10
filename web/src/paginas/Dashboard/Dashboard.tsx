import { useRef, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { obterEstatisticas } from "../../api/dashboard";
import { listarNotas, progressoLote, uploadNotas } from "../../api/notas";
import type { StatusNota } from "../../api/tipos";
import { ErroApi } from "../../api/cliente";
import { useToast } from "../../componentes/Toast";
import { Select } from "../../componentes/Select";
import { CardMetrica } from "../../componentes/CardMetrica";
import { Card } from "../../componentes/Card";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { Paginacao } from "../../componentes/Paginacao";
import estilos from "./Dashboard.module.css";

// Mapeia o enum do backend para as variantes de badge do protótipo -- lá
// "duplicado" corresponde ao estado neutro (rótulo "Duplicado").
const STATUS_PARA_BADGE: Record<StatusNota, StatusBadge> = {
  sucesso: "sucesso",
  pendente: "pendente",
  erro: "erro",
  duplicado: "neutro",
};

// GET /api/notas só aceita valores do enum StatusProcessamento -- um valor
// fora disso estoura 500 no backend, porque routes_notas.py:32 não trata
// ValueError como as rotas de /produtos/sugestoes tratam. "" representa
// "sem filtro" só no front (ver frontend/paginas/dashboard.py:15).
const OPCOES_STATUS: { valor: StatusNota | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Todos" },
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "sucesso", rotulo: "Sucesso" },
  { valor: "erro", rotulo: "Erro" },
  { valor: "duplicado", rotulo: "Duplicado" },
];

const LIMITE_NOTAS = 20;

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
  const { notificar } = useToast();
  const queryClient = useQueryClient();

  const [cnpjCliente, setCnpjCliente] = useState("");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [loteId, setLoteId] = useState<string | null>(null);
  const inputArquivosRef = useRef<HTMLInputElement>(null);

  const [statusFiltro, setStatusFiltro] = useState<StatusNota | "">("");
  const [offset, setOffset] = useState(0);

  const estatisticas = useQuery({
    queryKey: ["dashboard-estatisticas", casoIdNumero],
    queryFn: () => obterEstatisticas(casoIdNumero),
  });

  const upload = useMutation({
    mutationFn: () => uploadNotas(casoIdNumero, cnpjCliente, arquivos),
    onSuccess: (resposta) => {
      setLoteId(resposta.lote_id);
      notificar(`Lote enviado: ${resposta.total_arquivos} arquivo(s) em processamento.`);
      setArquivos([]);
    },
    onError: (erro) => {
      notificar(erro instanceof ErroApi ? erro.message : "Erro no upload.", "erro");
    },
  });

  const progresso = useQuery({
    queryKey: ["progresso-lote", loteId],
    queryFn: () => progressoLote(loteId as string),
    enabled: loteId !== null,
    // Substitui o botão "Atualizar" do Streamlit (dashboard.py:84-88):
    // reconsulta sozinho enquanto o lote não terminar, e para quando
    // concluidos === total_arquivos.
    refetchInterval: (query) => {
      const dados = query.state.data;
      if (!dados || dados.concluidos < dados.total_arquivos) return 2000;
      return false;
    },
  });

  const notas = useQuery({
    queryKey: ["notas", casoIdNumero, statusFiltro, offset],
    queryFn: () =>
      listarNotas({
        clienteCasoId: casoIdNumero,
        status: statusFiltro || undefined,
        limit: LIMITE_NOTAS,
        offset,
      }),
  });

  function handleSubmitUpload(evento: FormEvent) {
    evento.preventDefault();
    if (!cnpjCliente || arquivos.length === 0) {
      notificar("Informe o CNPJ do cliente e selecione ao menos um arquivo XML.", "erro");
      return;
    }
    upload.mutate();
  }

  function handleMudarStatus(novoStatus: StatusNota | "") {
    setStatusFiltro(novoStatus);
    setOffset(0);
  }

  function handleAtualizarTudo() {
    queryClient.invalidateQueries({ queryKey: ["dashboard-estatisticas", casoIdNumero] });
    queryClient.invalidateQueries({ queryKey: ["notas", casoIdNumero] });
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

      <form onSubmit={handleSubmitUpload} className={estilos.formUpload}>
        <CampoTexto
          rotulo="CNPJ do cliente (só números)"
          value={cnpjCliente}
          onChange={(evento) => setCnpjCliente(evento.target.value)}
        />
        <div className={estilos.dropArea} onClick={() => inputArquivosRef.current?.click()}>
          <input
            ref={inputArquivosRef}
            type="file"
            accept=".xml"
            multiple
            className={estilos.inputArquivos}
            onChange={(evento) => setArquivos(Array.from(evento.target.files ?? []))}
          />
          <div className={estilos.dropAreaIcone} />
          <span className={estilos.dropAreaTitulo}>
            {arquivos.length > 0 ? `${arquivos.length} arquivo(s) selecionado(s)` : "Arraste arquivos XML aqui ou clique para selecionar"}
          </span>
          <span className={estilos.dropAreaSubtitulo}>Suporta upload em lote de notas fiscais eletrônicas (NF-e)</span>
          <Botao
            type="button"
            variante="secundario"
            onClick={(evento) => {
              evento.stopPropagation();
              inputArquivosRef.current?.click();
            }}
          >
            Selecionar arquivos
          </Botao>
        </div>
        <Botao type="submit" disabled={upload.isPending}>
          {upload.isPending ? "Enviando..." : "Enviar lote"}
        </Botao>
      </form>

      {loteId && (
        <Card>
          <h2 className={estilos.tituloSecao}>Progresso do último lote enviado</h2>
          {progresso.data && (
            <>
              <p>
                {progresso.data.concluidos} de {progresso.data.total_arquivos} concluído(s) -- {progresso.data.com_erro} com
                erro.
              </p>
              {/* Lista arquivo a arquivo com motivo_erro: é o que explica a falha de
                  parsing de um XML específico -- ele nunca chega a virar uma Nota
                  nesse caso, então o badge de status por nota não conta essa
                  história (ver frontend/paginas/dashboard.py:97-99). */}
              <ul className={estilos.listaArquivos}>
                {progresso.data.arquivos.map((arquivo) => (
                  <li key={arquivo.id}>
                    <strong>{arquivo.nome_arquivo}</strong>: {arquivo.status}
                    {arquivo.motivo_erro && <> -- {arquivo.motivo_erro}</>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}

      <Card>
        <div className={estilos.cabecalhoNotas}>
          <h2 className={estilos.tituloSecao}>Notas recentes</h2>
          <Select
            valor={statusFiltro}
            opcoes={OPCOES_STATUS}
            onMudar={handleMudarStatus}
            rotuloAria="Filtrar por status"
          />
        </div>

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
