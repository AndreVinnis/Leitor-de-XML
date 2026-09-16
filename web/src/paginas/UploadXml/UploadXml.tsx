import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { progressoLote, uploadNotas } from "../../api/notas";
import { ErroApi } from "../../api/cliente";
import { useCasos } from "../../casos/ContextoCaso";
import { useToast } from "../../componentes/Toast";
import { Card } from "../../componentes/Card";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Paginacao } from "../../componentes/Paginacao";
import { formatarCnpj } from "../../utilitarios/formatarCnpj";
import type { StatusNota } from "../../api/tipos";
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

// Último lote enviado por caso, para o card de progresso sobreviver a sair
// da tela e voltar (navegação, F5) -- sem isso, `loteId` vivia só no estado
// do componente e sumia ao desmontar, escondendo até nota com erro atrás de
// "nenhum lote enviado ainda". sessionStorage porque é o mesmo padrão já
// usado pro usuário logado (ver auth/ContextoAuth.tsx): sobrevive à
// navegação, não precisa sobreviver ao fechar a aba.
function chaveUltimoLote(casoId: number): string {
  return `ultimo_lote_caso_${casoId}`;
}

function lerUltimoLote(casoId: number): string | null {
  try {
    return sessionStorage.getItem(chaveUltimoLote(casoId));
  } catch {
    return null;
  }
}

function salvarUltimoLote(casoId: number, loteId: string) {
  try {
    sessionStorage.setItem(chaveUltimoLote(casoId), loteId);
  } catch {
    /* sessionStorage indisponível (aba privada etc.) -- segue sem persistir */
  }
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
  const [loteId, setLoteId] = useState<string | null>(null);
  const [offsetProgresso, setOffsetProgresso] = useState(0);
  const [arrastando, setArrastando] = useState(false);
  const inputArquivosRef = useRef<HTMLInputElement>(null);

  // A rota é a mesma ao trocar de caso (casos/:casoId/upload não remonta o
  // componente, só troca o param), então recarrega o último lote desse caso
  // aqui em vez de num lazy initializer do useState -- cobre tanto o mount
  // inicial quanto a troca de caso pelo seletor do topo.
  useEffect(() => {
    setLoteId(lerUltimoLote(casoIdNumero));
  }, [casoIdNumero]);

  // Reseta a paginação quando a lista muda de "fonte" -- lote novo enviado,
  // ou lista de arquivos selecionados esvaziada (após envio) -- senão o
  // offset antigo pode ficar além do novo total e não mostrar nada.
  useEffect(() => {
    setOffsetProgresso(0);
  }, [loteId]);

  useEffect(() => {
    if (arquivos.length === 0) setOffsetArquivos(0);
  }, [arquivos.length]);

  const upload = useMutation({
    mutationFn: () => uploadNotas(casoIdNumero, casoAtivo!.cnpj_cliente!, arquivos),
    onSuccess: (resposta) => {
      setLoteId(resposta.lote_id);
      salvarUltimoLote(casoIdNumero, resposta.lote_id);
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
    // Reconsulta sozinho enquanto o lote não terminar, e para quando
    // concluidos === total_arquivos (mesmo padrão do Dashboard).
    refetchInterval: (query) => {
      const dados = query.state.data;
      if (!dados || dados.concluidos < dados.total_arquivos) return 2000;
      return false;
    },
  });

  function adicionarArquivos(novos: FileList | null) {
    if (!novos || novos.length === 0) return;
    setArquivos((atuais) => [...atuais, ...Array.from(novos)]);
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
          onClick={() => inputArquivosRef.current?.click()}
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
          <div className={estilos.dropAreaIcone} />
          <span className={estilos.dropAreaTitulo}>Arraste arquivos XML aqui ou clique para selecionar</span>
          <span className={estilos.dropAreaSubtitulo}>Suporta upload em lote de notas fiscais eletrônicas (NF-e)</span>
          <span className={estilos.dropAreaLimite}>Limite máximo suportado de 500 notas por lote</span>
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

        {arquivos.length > 0 && (
          <Card>
            <div className={estilos.cabecalhoArquivos}>
              <h2 className={estilos.tituloSecao}>Arquivos selecionados</h2>
              <button type="button" className={estilos.botaoRemoverTodos} onClick={removerTodosArquivos}>
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
              </span>
              <Botao type="submit" disabled={upload.isPending || !casoAtivo?.cnpj_cliente}>
                {upload.isPending ? "Enviando..." : "Enviar lote"}
              </Botao>
            </div>
          </Card>
        )}
      </form>

      <Card>
        <h2 className={estilos.tituloSecao}>Progresso do lote</h2>
        {progresso.data ? (
          <div className={estilos.progresso}>
            <div className={estilos.barraProgresso}>
              <div
                className={estilos.barraProgressoPreenchimento}
                style={{
                  width: `${progresso.data.total_arquivos > 0 ? (progresso.data.concluidos / progresso.data.total_arquivos) * 100 : 0}%`,
                }}
              />
            </div>
            <p className={estilos.progressoResumo}>
              {progresso.data.concluidos} de {progresso.data.total_arquivos} concluídos · {progresso.data.com_erro}{" "}
              com erro
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
              {progresso.data.arquivos.slice(offsetProgresso, offsetProgresso + ITENS_POR_PAGINA).map((arquivo) => (
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
              total={progresso.data.arquivos.length}
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
