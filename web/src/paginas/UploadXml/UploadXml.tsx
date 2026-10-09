import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQueries, type UseQueryResult } from "@tanstack/react-query";
import { dividirEmPartes, LIMITE_BYTES_POR_ARQUIVO, progressoLote, uploadNotas } from "../../api/notas";
import { ErroApi } from "../../api/cliente";
import { useCasos } from "../../casos/ContextoCaso";
import { useToast } from "../../componentes/Toast";
import { Card } from "../../componentes/Card";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Paginacao } from "../../componentes/Paginacao";
import { formatarCnpj } from "../../utilitarios/formatarCnpj";
import type { ArquivoLoteProgresso, ProgressoLote, StatusNota } from "../../api/tipos";
import estilos from "./UploadXml.module.css";

const ITENS_POR_PAGINA = 30;

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusParaBadge(status: StatusNota | null): StatusBadge {
  return status === "duplicado" ? "neutro" : status ?? "pendente";
}

// Lotes do último envio por caso, para o card de progresso sobreviver a sair
// da tela e voltar (navegação, F5) -- sem isso, os ids viviam só no estado
// do componente e sumiam ao desmontar, escondendo até nota com erro atrás de
// "nenhum lote enviado ainda". sessionStorage porque é o mesmo padrão já
// usado pro usuário logado (ver auth/ContextoAuth.tsx): sobrevive à
// navegação, não precisa sobreviver ao fechar a aba. É uma lista porque um
// envio grande vira vários lotes (um por parte, ver dividirEmPartes).
function chaveUltimosLotes(casoId: number): string {
  return `ultimos_lotes_caso_${casoId}`;
}

// Chave de antes do envio em partes (um id só). Lida como fallback para não
// sumir o card de quem já tinha um lote aberto na aba.
function chaveUltimoLoteLegado(casoId: number): string {
  return `ultimo_lote_caso_${casoId}`;
}

function lerUltimosLotes(casoId: number): string[] {
  try {
    const salvo = sessionStorage.getItem(chaveUltimosLotes(casoId));
    if (salvo) {
      const lista: unknown = JSON.parse(salvo);
      if (Array.isArray(lista)) return lista.filter((id): id is string => typeof id === "string");
    }
    const legado = sessionStorage.getItem(chaveUltimoLoteLegado(casoId));
    return legado ? [legado] : [];
  } catch {
    return [];
  }
}

function salvarUltimosLotes(casoId: number, loteIds: string[]) {
  try {
    sessionStorage.setItem(chaveUltimosLotes(casoId), JSON.stringify(loteIds));
    sessionStorage.removeItem(chaveUltimoLoteLegado(casoId));
  } catch {
    /* sessionStorage indisponível (aba privada etc.) -- segue sem persistir */
  }
}

// Identifica o mesmo arquivo escolhido duas vezes (ex: a mesma pasta
// selecionada de novo). webkitRelativePath só vem preenchido na seleção de
// pasta, e distingue arquivos de mesmo nome em subpastas diferentes.
function chaveArquivo(arquivo: File): string {
  return `${arquivo.webkitRelativePath || arquivo.name}|${arquivo.size}|${arquivo.lastModified}`;
}

interface ProgressoEnvio {
  partes: number;
  total_arquivos: number;
  concluidos: number;
  com_erro: number;
  arquivos: ArquivoLoteProgresso[];
}

// Soma os lotes já carregados do envio. Fora do componente para o `combine`
// do useQueries ter referência estável (senão recalcula a cada render).
function agregarProgresso(resultados: UseQueryResult<ProgressoLote>[]): ProgressoEnvio | null {
  const lotes = resultados.flatMap((resultado) => (resultado.data ? [resultado.data] : []));
  if (lotes.length === 0) return null;
  return {
    partes: lotes.length,
    total_arquivos: lotes.reduce((soma, lote) => soma + lote.total_arquivos, 0),
    concluidos: lotes.reduce((soma, lote) => soma + lote.concluidos, 0),
    com_erro: lotes.reduce((soma, lote) => soma + lote.com_erro, 0),
    arquivos: lotes.flatMap((lote) => lote.arquivos),
  };
}

export function UploadXml() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const { casos } = useCasos();
  const casoAtivo = casos.find((caso) => String(caso.id) === casoId);
  const { notificar } = useToast();

  const [arquivos, setArquivos] = useState<File[]>([]);
  // Muda a cada seleção para forçar o React a remontar o <input type="file">
  // com um nó DOM novo a cada abertura do diálogo nativo -- reaproveitar o
  // mesmo input entre seleções (só resetando `.value`) deixava a segunda
  // abertura do diálogo "morta" em alguns ambientes (ex: antivírus que
  // intercepta o diálogo de arquivo), sem disparar onChange de novo.
  const [inputKey, setInputKey] = useState(0);
  const [offsetArquivos, setOffsetArquivos] = useState(0);
  const [loteIds, setLoteIds] = useState<string[]>([]);
  const [offsetProgresso, setOffsetProgresso] = useState(0);
  const [arrastando, setArrastando] = useState(false);
  // Parte em envio agora, para o texto do botão ("Enviando parte 2 de 5...").
  const [partesEnvio, setPartesEnvio] = useState<{ atual: number; total: number } | null>(null);
  // Uma parte falhou depois de outras já terem subido: os arquivos que
  // faltam continuam na lista, e o próximo envio anexa à lista de lotes em
  // vez de substituí-la (senão o card perderia as partes já enviadas).
  const [envioIncompleto, setEnvioIncompleto] = useState(false);
  const inputArquivosRef = useRef<HTMLInputElement>(null);
  const inputPastaRef = useRef<HTMLInputElement | null>(null);
  // Caso que a tela mostra agora. O envio em partes é longo e o usuário pode
  // trocar de caso no meio: as partes seguem indo para o caso de origem, mas
  // só mexem no estado da tela se ela ainda estiver nesse caso.
  const casoAtualRef = useRef(casoIdNumero);

  // A rota é a mesma ao trocar de caso (casos/:casoId/upload não remonta o
  // componente, só troca o param), então recarrega os lotes desse caso
  // aqui em vez de num lazy initializer do useState -- cobre tanto o mount
  // inicial quanto a troca de caso pelo seletor do topo. Também esvazia a
  // seleção: os arquivos escolhidos são do caso anterior, e enviá-los com o
  // CNPJ do caso novo misturaria XMLs de clientes diferentes.
  useEffect(() => {
    casoAtualRef.current = casoIdNumero;
    setLoteIds(lerUltimosLotes(casoIdNumero));
    setArquivos([]);
    setEnvioIncompleto(false);
  }, [casoIdNumero]);

  // Reseta a paginação quando a lista de lotes muda (envio novo ou parte
  // nova), senão o offset antigo pode ficar além do novo total.
  useEffect(() => {
    setOffsetProgresso(0);
  }, [loteIds]);

  // A lista de selecionados encolhe a cada parte enviada: puxa o offset de
  // volta para a última página que ainda existe.
  useEffect(() => {
    if (offsetArquivos >= arquivos.length) {
      setOffsetArquivos(Math.max(0, Math.floor((arquivos.length - 1) / ITENS_POR_PAGINA) * ITENS_POR_PAGINA));
    }
  }, [arquivos.length, offsetArquivos]);

  useEffect(() => {
    if (arquivos.length === 0) setEnvioIncompleto(false);
  }, [arquivos.length]);

  const upload = useMutation({
    mutationFn: async () => {
      // Captura caso, CNPJ e arquivos no início: o laço dura vários
      // requests e nada disso pode mudar no meio.
      const casoEnvio = casoIdNumero;
      const cnpjEnvio = casoAtivo!.cnpj_cliente!;
      const partes = dividirEmPartes(arquivos);
      const naMesmaTela = () => casoAtualRef.current === casoEnvio;
      let ids = envioIncompleto ? loteIds : [];
      let enviados = 0;

      for (let indice = 0; indice < partes.length; indice++) {
        const parte = partes[indice];
        if (naMesmaTela()) setPartesEnvio({ atual: indice + 1, total: partes.length });
        try {
          const resposta = await uploadNotas(casoEnvio, cnpjEnvio, parte);
          ids = [...ids, resposta.lote_id];
          enviados += resposta.total_arquivos;
        } catch (erro) {
          const motivo = erro instanceof ErroApi ? erro.message : "Erro no upload.";
          if (partes.length === 1) throw new Error(motivo);
          const restantes = partes.slice(indice).reduce((soma, p) => soma + p.length, 0);
          // Fora da tela do caso de origem a seleção já foi esvaziada (ver o
          // effect de troca de caso), então não há o que continuar daqui.
          if (!naMesmaTela()) {
            throw new Error(
              `Parte ${indice + 1} de ${partes.length} falhou: ${motivo} ` +
                `${restantes} arquivo(s) não foram enviados. Selecione-os de novo no caso de origem.`
            );
          }
          if (ids.length > 0) setEnvioIncompleto(true);
          throw new Error(
            `Parte ${indice + 1} de ${partes.length} falhou: ${motivo} ` +
              `${restantes} arquivo(s) ainda não enviado(s) continuam na lista.`
          );
        }
        // Persiste a cada parte, não só no fim: se a aba cair no meio, o card
        // ainda mostra o que já subiu.
        salvarUltimosLotes(casoEnvio, ids);
        const enviadosDaParte = new Set(parte);
        if (naMesmaTela()) {
          setLoteIds(ids);
          setArquivos((atuais) => atuais.filter((arquivo) => !enviadosDaParte.has(arquivo)));
        }
      }
      return { enviados, partes: partes.length };
    },
    onSuccess: ({ enviados, partes }) => {
      setEnvioIncompleto(false);
      notificar(
        partes > 1
          ? `Envio concluído: ${enviados} arquivo(s) em ${partes} partes, em processamento.`
          : `Lote enviado: ${enviados} arquivo(s) em processamento.`
      );
    },
    onError: (erro) => {
      notificar(erro.message, "erro");
    },
    onSettled: () => setPartesEnvio(null),
  });

  // O envio é conduzido pelo navegador: fechar ou recarregar a aba no meio
  // interrompe as partes que faltam. Avisa só enquanto há envio em curso.
  useEffect(() => {
    if (!upload.isPending) return;
    const avisarSaida = (evento: BeforeUnloadEvent) => {
      evento.preventDefault();
      evento.returnValue = "";
    };
    window.addEventListener("beforeunload", avisarSaida);
    return () => window.removeEventListener("beforeunload", avisarSaida);
  }, [upload.isPending]);

  const progresso = useQueries({
    queries: loteIds.map((id) => ({
      queryKey: ["progresso-lote", id],
      queryFn: () => progressoLote(id),
      // Reconsulta sozinho enquanto o lote não terminar, e para quando
      // concluidos === total_arquivos (mesmo padrão do Dashboard). Cada lote
      // para por conta própria, então partes já concluídas param de consultar.
      // Lote que deu erro (ex: id velho no sessionStorage, 404) também para,
      // senão seria reconsultado a cada 2 s para sempre.
      refetchInterval: (query: { state: { data?: ProgressoLote; status: string } }) => {
        if (query.state.status === "error") return false;
        const dados = query.state.data;
        if (!dados || dados.concluidos < dados.total_arquivos) return 2000;
        return false;
      },
    })),
    combine: agregarProgresso,
  });

  const totalPartes = useMemo(() => dividirEmPartes(arquivos).length, [arquivos]);

  function adicionarArquivos(novos: FileList | null) {
    if (!novos || novos.length === 0) return;
    if (upload.isPending) {
      notificar("Aguarde o envio em andamento terminar para adicionar mais arquivos.", "erro");
      return;
    }
    // O backend recusa o lote inteiro se houver um arquivo que não seja
    // .xml (routes_upload._nome_arquivo_seguro) ou que passe do teto por
    // arquivo (413). O diálogo já filtra por accept=".xml", mas a seleção de
    // pasta e o arrastar e soltar não -- filtra aqui e avisa o que ficou de fora.
    const lista = Array.from(novos);
    const xmls = lista.filter((arquivo) => arquivo.name.toLowerCase().endsWith(".xml"));
    const naoXml = lista.length - xmls.length;
    if (naoXml > 0) {
      notificar(`${naoXml} arquivo(s) ignorado(s) por não serem .xml.`, "erro");
    }
    const cabem = xmls.filter((arquivo) => arquivo.size <= LIMITE_BYTES_POR_ARQUIVO);
    const grandes = xmls.length - cabem.length;
    if (grandes > 0) {
      notificar(
        `${grandes} arquivo(s) ignorado(s) por passarem de ${LIMITE_BYTES_POR_ARQUIVO / (1024 * 1024)} MB.`,
        "erro"
      );
    }
    const vistos = new Set(arquivos.map(chaveArquivo));
    const unicos = cabem.filter((arquivo) => {
      const chave = chaveArquivo(arquivo);
      if (vistos.has(chave)) return false;
      vistos.add(chave);
      return true;
    });
    const repetidos = cabem.length - unicos.length;
    if (repetidos > 0) {
      notificar(`${repetidos} arquivo(s) já estavam na lista e não foram adicionados de novo.`);
    }
    if (unicos.length === 0) return;
    setArquivos((atuais) => [...atuais, ...unicos]);
  }

  function removerArquivo(indice: number) {
    setArquivos((atuais) => atuais.filter((_, i) => i !== indice));
  }

  function removerTodosArquivos() {
    setArquivos([]);
  }

  function handleDrop(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault();
    setArrastando(false);
    adicionarArquivos(evento.dataTransfer.files);
  }

  function handleSubmitUpload(evento: FormEvent) {
    evento.preventDefault();
    if (!casoAtivo?.cnpj_cliente || arquivos.length === 0) {
      notificar("Este caso precisa ter um CNPJ cadastrado e ao menos um arquivo XML selecionado.", "erro");
      return;
    }
    upload.mutate();
  }

  const tamanhoTotal = arquivos.reduce((soma, arquivo) => soma + arquivo.size, 0);

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Upload de XML</h1>
        <p className={estilos.subtitulo}>Envie em lote os XMLs de NF-e de entrada e saída do caso selecionado</p>
      </div>

      <div className={estilos.linhaCamposCaso}>
        <CampoTexto
          rotulo="Nome do Cliente"
          placeholder="Nome do cliente"
          value={casoAtivo?.nome_cliente ?? ""}
          disabled
          className={estilos.campoInfoCaso}
        />
        <CampoTexto
          rotulo="CNPJ do cliente"
          placeholder="00.000.000/0000-00"
          value={formatarCnpj(casoAtivo?.cnpj_cliente)}
          disabled
          className={estilos.campoInfoCaso}
        />
      </div>
      {casoAtivo && !casoAtivo.cnpj_cliente && (
        <p className={estilos.avisoCnpjAusente}>
          Este caso ainda não tem CNPJ cadastrado. Edite o caso no seletor do topo para adicionar um antes de
          enviar XMLs.
        </p>
      )}

      <form onSubmit={handleSubmitUpload}>
        <div
          className={`${estilos.dropArea} ${arrastando ? estilos.dropAreaArrastando : ""}`}
          onClick={(evento) => {
            // O .click() programático nos inputs ocultos sobe até aqui: sem
            // este filtro, "Selecionar pasta" abriria o diálogo de arquivos.
            if (evento.target instanceof HTMLInputElement) return;
            inputArquivosRef.current?.click();
          }}
          onDragOver={(evento) => {
            evento.preventDefault();
            setArrastando(true);
          }}
          onDragLeave={() => setArrastando(false)}
          onDrop={handleDrop}
        >
          <input
            key={inputKey}
            ref={inputArquivosRef}
            type="file"
            accept=".xml"
            multiple
            className={estilos.inputArquivos}
            onChange={(evento) => {
              adicionarArquivos(evento.target.files);
              setInputKey((atual) => atual + 1);
            }}
          />
          <input
            key={`pasta-${inputKey}`}
            // webkitdirectory não existe nos tipos do React: aplicado direto no
            // nó. Callback ref porque o input é remontado a cada seleção (key).
            ref={(no) => {
              inputPastaRef.current = no;
              no?.setAttribute("webkitdirectory", "");
            }}
            type="file"
            multiple
            className={estilos.inputArquivos}
            onChange={(evento) => {
              adicionarArquivos(evento.target.files);
              setInputKey((atual) => atual + 1);
            }}
          />
          <div className={estilos.dropAreaIcone} />
          <span className={estilos.dropAreaTitulo}>Arraste arquivos XML aqui ou clique para selecionar</span>
          <span className={estilos.dropAreaSubtitulo}>Suporta upload em lote de notas fiscais eletrônicas (NF-e)</span>
          <span className={estilos.dropAreaLimite}>
            Pastas grandes são enviadas automaticamente em partes de até 999 notas
          </span>
          <div className={estilos.botoesSelecao}>
            <Botao
              type="button"
              variante="secundario"
              disabled={upload.isPending}
              onClick={(evento) => {
                evento.stopPropagation();
                inputArquivosRef.current?.click();
              }}
            >
              Selecionar arquivos
            </Botao>
            <Botao
              type="button"
              variante="secundario"
              disabled={upload.isPending}
              onClick={(evento) => {
                evento.stopPropagation();
                inputPastaRef.current?.click();
              }}
            >
              Selecionar pasta
            </Botao>
          </div>
        </div>

        {arquivos.length > 0 && (
          <Card>
            <div className={estilos.cabecalhoArquivos}>
              <h2 className={estilos.tituloSecao}>Arquivos selecionados</h2>
              <button
                type="button"
                className={estilos.botaoRemoverTodos}
                onClick={removerTodosArquivos}
                disabled={upload.isPending}
              >
                Remover todos
              </button>
            </div>
            <div className={estilos.tabelaArquivos}>
              {arquivos.slice(offsetArquivos, offsetArquivos + ITENS_POR_PAGINA).map((arquivo, indice) => {
                const indiceReal = offsetArquivos + indice;
                return (
                  <div key={`${arquivo.name}-${indiceReal}`} className={estilos.linhaArquivo}>
                    <span className={estilos.nomeArquivo}>{arquivo.name}</span>
                    <span className={estilos.tamanhoArquivo}>{formatarTamanho(arquivo.size)}</span>
                    <button
                      type="button"
                      className={estilos.botaoRemover}
                      onClick={() => removerArquivo(indiceReal)}
                      disabled={upload.isPending}
                      aria-label={`Remover ${arquivo.name}`}
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
            <Paginacao offset={offsetArquivos} limite={ITENS_POR_PAGINA} total={arquivos.length} onMudar={setOffsetArquivos} />
            <div className={estilos.rodapeArquivos}>
              <span className={estilos.contagemArquivos}>
                {arquivos.length} arquivo(s) · {formatarTamanho(tamanhoTotal)}
                {totalPartes > 1 && ` · será enviado em ${totalPartes} partes`}
              </span>
              <Botao type="submit" disabled={upload.isPending || !casoAtivo?.cnpj_cliente}>
                {upload.isPending
                  ? partesEnvio && partesEnvio.total > 1
                    ? `Enviando parte ${partesEnvio.atual} de ${partesEnvio.total}...`
                    : "Enviando..."
                  : envioIncompleto
                    ? "Continuar envio"
                    : "Enviar lote"}
              </Botao>
            </div>
          </Card>
        )}
      </form>

      <Card>
        <h2 className={estilos.tituloSecao}>Progresso do envio</h2>
        {progresso ? (
          <div className={estilos.progresso}>
            <div className={estilos.barraProgresso}>
              <div
                className={estilos.barraProgressoPreenchimento}
                style={{
                  width: `${progresso.total_arquivos > 0 ? (progresso.concluidos / progresso.total_arquivos) * 100 : 0}%`,
                }}
              />
            </div>
            <p className={estilos.progressoResumo}>
              {progresso.concluidos} de {progresso.total_arquivos} concluídos · {progresso.com_erro} com erro
              {progresso.partes > 1 && ` · ${progresso.partes} partes`}
            </p>
            {/* Motivo do erro é o que explica a falha de parsing de um XML
                específico -- ele nunca chega a virar uma Nota nesse caso,
                então o badge de status por nota não conta essa história
                (ver frontend/paginas/dashboard.py:97-99). */}
            <div className={estilos.tabelaProgresso}>
              <div className={estilos.cabecalhoTabelaProgresso}>
                <span>ARQUIVO</span>
                <span>STATUS</span>
                <span>MOTIVO DO ERRO</span>
              </div>
              {progresso.arquivos.slice(offsetProgresso, offsetProgresso + ITENS_POR_PAGINA).map((arquivo) => (
                <div key={arquivo.id} className={estilos.linhaProgresso}>
                  <span className={estilos.nomeArquivoProgresso}>{arquivo.nome_arquivo}</span>
                  <span>
                    <Badge status={statusParaBadge(arquivo.status)} />
                  </span>
                  <span className={estilos.motivoErroProgresso}>{arquivo.motivo_erro}</span>
                </div>
              ))}
            </div>
            <Paginacao
              offset={offsetProgresso}
              limite={ITENS_POR_PAGINA}
              total={progresso.arquivos.length}
              onMudar={setOffsetProgresso}
            />
          </div>
        ) : (
          <div className={estilos.estadoVazio}>
            <div className={estilos.estadoVazioIcone} />
            <p className={estilos.estadoVazioTitulo}>Nenhum lote enviado ainda</p>
            <p className={estilos.estadoVazioTexto}>O progresso do processamento aparece aqui depois que você enviar os arquivos.</p>
          </div>
        )}
      </Card>
    </div>
  );
}
