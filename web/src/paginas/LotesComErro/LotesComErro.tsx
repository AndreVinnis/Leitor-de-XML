import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listarLotesComErro, progressoLote } from "../../api/notas";
import { Botao } from "../../componentes/Botao";
import { Card } from "../../componentes/Card";
import { Paginacao } from "../../componentes/Paginacao";
import estilos from "./LotesComErro.module.css";

const LIMITE = 20;

export function LotesComErro() {
  const { casoId } = useParams<{ casoId: string }>();
  const casoIdNumero = Number(casoId);
  const [offset, setOffset] = useState(0);
  const [loteExpandidoId, setLoteExpandidoId] = useState<string | null>(null);

  const lotes = useQuery({
    queryKey: ["lotes-com-erro", casoIdNumero, offset],
    queryFn: () => listarLotesComErro({ clienteCasoId: casoIdNumero, limit: LIMITE, offset }),
  });

  const detalheLoteExpandido = useQuery({
    queryKey: ["progresso-lote", loteExpandidoId],
    queryFn: () => progressoLote(loteExpandidoId as string),
    enabled: loteExpandidoId !== null,
  });

  function alternarExpandido(loteId: string) {
    setLoteExpandidoId((atual) => (atual === loteId ? null : loteId));
  }

  const arquivosComErro =
    detalheLoteExpandido.data?.arquivos.filter((arquivo) => arquivo.status === "erro") ?? [];

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Lotes com erro</h1>
        <p className={estilos.subtitulo}>Lotes que tiveram ao menos um arquivo com erro no processamento</p>
      </div>

      <Card>
        <div className={estilos.tabela}>
          <div className={estilos.cabecalhoTabela}>
            <span>DATA/HORA</span>
            <span>LOTE</span>
            <span>USUÁRIO</span>
            <span>ARQUIVOS COM ERRO</span>
            <span />
          </div>

          {lotes.data?.itens.length === 0 && (
            <p className={estilos.vazio}>Nenhum lote com erro encontrado.</p>
          )}

          {lotes.data?.itens.map((lote) => {
            const expandido = loteExpandidoId === lote.id;
            return (
              <div key={lote.id} className={estilos.grupoLinha}>
                <div className={estilos.linha}>
                  <span>{new Date(lote.criado_em).toLocaleString("pt-BR")}</span>
                  <span className={estilos.codigoLote}>#{lote.id.slice(0, 8)}</span>
                  <span>{lote.usuario_nome ?? "—"}</span>
                  <span>
                    {lote.arquivos_com_erro} de {lote.total_arquivos}
                  </span>
                  <Botao type="button" variante="secundario" onClick={() => alternarExpandido(lote.id)}>
                    {expandido ? "Ocultar arquivos" : "Ver arquivos com erro"}
                  </Botao>
                </div>

                {expandido && (
                  <div className={estilos.subTabela}>
                    <div className={estilos.cabecalhoSubTabela}>
                      <span>ARQUIVO</span>
                      <span>MOTIVO DO ERRO</span>
                    </div>
                    {detalheLoteExpandido.isLoading && (
                      <p className={estilos.vazio}>Carregando arquivos...</p>
                    )}
                    {!detalheLoteExpandido.isLoading &&
                      arquivosComErro.map((arquivo) => (
                        <div key={arquivo.id} className={estilos.linhaSubTabela}>
                          <span className={estilos.nomeArquivo}>{arquivo.nome_arquivo}</span>
                          <span className={estilos.motivoErro}>{arquivo.motivo_erro}</span>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {lotes.data && <Paginacao offset={offset} limite={LIMITE} total={lotes.data.total} onMudar={setOffset} />}
      </Card>
    </div>
  );
}
