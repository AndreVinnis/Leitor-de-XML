import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { progressoLote, uploadNotas } from "../../api/notas";
import { ErroApi } from "../../api/cliente";
import { useToast } from "../../componentes/Toast";
import { Card } from "../../componentes/Card";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import estilos from "./UploadXml.module.css";

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadXml() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const { notificar } = useToast();

  const [cnpjCliente, setCnpjCliente] = useState("");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [loteId, setLoteId] = useState<string | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const inputArquivosRef = useRef<HTMLInputElement>(null);

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

  function handleDrop(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault();
    setArrastando(false);
    adicionarArquivos(evento.dataTransfer.files);
  }

  function handleSubmitUpload(evento: FormEvent) {
    evento.preventDefault();
    if (!cnpjCliente || arquivos.length === 0) {
      notificar("Informe o CNPJ do cliente e selecione ao menos um arquivo XML.", "erro");
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

      <CampoTexto
        rotulo="CNPJ do cliente"
        placeholder="00.000.000/0000-00"
        value={cnpjCliente}
        onChange={(evento) => setCnpjCliente(evento.target.value)}
        className={estilos.campoCnpj}
      />

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
            ref={inputArquivosRef}
            type="file"
            accept=".xml"
            multiple
            className={estilos.inputArquivos}
            onChange={(evento) => {
              adicionarArquivos(evento.target.files);
              evento.target.value = "";
            }}
          />
          <div className={estilos.dropAreaIcone} />
          <span className={estilos.dropAreaTitulo}>Arraste arquivos XML aqui ou clique para selecionar</span>
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

        {arquivos.length > 0 && (
          <Card>
            <h2 className={estilos.tituloSecao}>Arquivos selecionados</h2>
            <div className={estilos.tabelaArquivos}>
              {arquivos.map((arquivo, indice) => (
                <div key={`${arquivo.name}-${indice}`} className={estilos.linhaArquivo}>
                  <span className={estilos.nomeArquivo}>{arquivo.name}</span>
                  <span className={estilos.tamanhoArquivo}>{formatarTamanho(arquivo.size)}</span>
                  <button
                    type="button"
                    className={estilos.botaoRemover}
                    onClick={() => removerArquivo(indice)}
                    aria-label={`Remover ${arquivo.name}`}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <div className={estilos.rodapeArquivos}>
              <span className={estilos.contagemArquivos}>
                {arquivos.length} arquivo(s) · {formatarTamanho(tamanhoTotal)}
              </span>
              <Botao type="submit" disabled={upload.isPending}>
                {upload.isPending ? "Enviando..." : "Enviar lote"}
              </Botao>
            </div>
          </Card>
        )}
      </form>

      <Card>
        <h2 className={estilos.tituloSecao}>Progresso do lote</h2>
        {progresso.data ? (
          <>
            <p className={estilos.progressoResumo}>
              {progresso.data.concluidos} de {progresso.data.total_arquivos} concluído(s) -- {progresso.data.com_erro} com
              erro.
            </p>
            {/* Lista arquivo a arquivo com motivo_erro: é o que explica a falha de
                parsing de um XML específico -- ele nunca chega a virar uma Nota
                nesse caso, então o badge de status por nota não conta essa
                história (ver frontend/paginas/dashboard.py:97-99). */}
            <ul className={estilos.listaProgresso}>
              {progresso.data.arquivos.map((arquivo) => (
                <li key={arquivo.id}>
                  <strong>{arquivo.nome_arquivo}</strong>: {arquivo.status}
                  {arquivo.motivo_erro && <> -- {arquivo.motivo_erro}</>}
                </li>
              ))}
            </ul>
          </>
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
