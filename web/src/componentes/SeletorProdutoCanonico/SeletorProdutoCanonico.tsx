import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { criarCanonico, listarCanonicos } from "../../api/produtos";
import { ErroApi } from "../../api/cliente";
import type { ProdutoCanonico } from "../../api/tipos";
import { useCategoriasDoCaso } from "../../api/useCategoriasDoCaso";
import { Botao } from "../Botao";
import { CampoTexto } from "../CampoTexto";
import { Modal } from "../Modal";
import { Paginacao } from "../Paginacao";
import { SeletorCategoria } from "../SeletorCategoria";
import { useToast } from "../Toast";
import estilos from "./SeletorProdutoCanonico.module.css";

const LIMITE_POR_PAGINA = 20;
const QTD_CHIPS_CATEGORIA = 6;
// Valor interno do filtro de categoria para "Sem categoria" (nunca vai ao backend).
const SEM_CATEGORIA = "__sem_categoria__";

interface SeletorProdutoCanonicoProps {
  casoId: number;
  titulo: string;
  /** Cartão de contexto exibido abaixo do cabeçalho (item original, sugestão, aviso...). */
  contexto?: ReactNode;
  /** Produto que recebe a etiqueta "Sugestão da IA". */
  idDestacado?: number;
  /** Produtos que não podem ser escolhidos (filtrados no cliente). */
  idsExcluidos?: number[];
  /** Produto já selecionado ao abrir. */
  idInicial?: number;
  /** Nome do produto de `idInicial`, para o rodapé "Selecionado:" não mostrar "#id". */
  nomeInicial?: string;
  rotuloConfirmar: string;
  /** Permite criar um novo produto canônico no próprio modal. */
  permitirCriar?: boolean;
  /** Recebe apenas o id escolhido: quem chama decide qual rota de revisão acionar. */
  onConfirmar: (produtoCanonicoId: number) => Promise<void> | void;
  onFechar: () => void;
}

function destacarTrecho(nome: string, termo: string): ReactNode {
  const alvo = termo.trim();
  if (!alvo) return nome;
  const indice = nome.toLowerCase().indexOf(alvo.toLowerCase());
  if (indice < 0) return nome;
  return (
    <>
      {nome.slice(0, indice)}
      <strong className={estilos.trechoBuscado}>{nome.slice(indice, indice + alvo.length)}</strong>
      {nome.slice(indice + alvo.length)}
    </>
  );
}

export function SeletorProdutoCanonico({
  casoId,
  titulo,
  contexto,
  idDestacado,
  idsExcluidos,
  idInicial,
  nomeInicial,
  rotuloConfirmar,
  permitirCriar = true,
  onConfirmar,
  onFechar,
}: SeletorProdutoCanonicoProps) {
  const queryClient = useQueryClient();
  const { notificar } = useToast();

  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [categoria, setCategoria] = useState("");
  const [offset, setOffset] = useState(0);
  const [selecionadoId, setSelecionadoId] = useState<number | null>(idInicial ?? null);
  const [criando, setCriando] = useState(false);
  const [nomeNovo, setNomeNovo] = useState("");
  const [categoriaNovo, setCategoriaNovo] = useState("");
  const [salvando, setSalvando] = useState(false);
  // Nomes já vistos nas listagens, para mostrar "Selecionado: <nome>" mesmo
  // depois de a linha escolhida sair da página/filtro atual.
  const nomesConhecidos = useRef(
    new Map<number, string>(idInicial !== undefined && nomeInicial ? [[idInicial, nomeInicial]] : [])
  );

  useEffect(() => {
    const temporizador = setTimeout(() => {
      setBusca(buscaDigitada);
      setOffset(0);
    }, 300);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const categorias = useCategoriasDoCaso(casoId);
  const listaCategorias = categorias.data ?? [];

  const canonicos = useQuery({
    queryKey: ["canonicos-busca", casoId, busca, categoria, offset],
    queryFn: async () => {
      const resposta = await listarCanonicos({
        clienteCasoId: casoId,
        busca: busca || undefined,
        categoria: categoria && categoria !== SEM_CATEGORIA ? categoria : undefined,
        semCategoria: categoria === SEM_CATEGORIA,
        limit: LIMITE_POR_PAGINA,
        offset,
      });
      resposta.itens.forEach((c) => nomesConhecidos.current.set(c.id, c.nome_canonico));
      return resposta;
    },
    enabled: Number.isFinite(casoId),
    placeholderData: (anterior) => anterior,
  });

  // Chave estável: quem chama costuma passar um array novo a cada render.
  const chaveExcluidos = (idsExcluidos ?? []).join(",");
  const excluidos = useMemo(
    () => new Set(chaveExcluidos ? chaveExcluidos.split(",").map(Number) : []),
    [chaveExcluidos]
  );
  const itens = useMemo(
    () => (canonicos.data?.itens ?? []).filter((c) => !excluidos.has(c.id)),
    [canonicos.data, excluidos]
  );
  // Os excluídos são filtrados no cliente: desconta do total os que apareceram
  // nesta página (aproximação, os de outras páginas continuam contados).
  const removidosNaPagina = (canonicos.data?.itens.length ?? 0) - itens.length;
  const total = Math.max(0, (canonicos.data?.total ?? 0) - removidosNaPagina);

  const nomeSelecionado = selecionadoId !== null ? nomesConhecidos.current.get(selecionadoId) : undefined;

  function mudarCategoria(valor: string) {
    setCategoria(valor);
    setOffset(0);
  }

  function rotuloCategoriaAtual() {
    if (categoria === SEM_CATEGORIA) return "Sem categoria";
    return categoria || "Todas";
  }

  function abrirCriacao(nomeInicial = "") {
    setNomeNovo(nomeInicial);
    setCriando(true);
  }

  function tentarFechar() {
    if (salvando) return;
    onFechar();
  }

  async function confirmar(produtoCanonicoId: number) {
    setSalvando(true);
    try {
      await onConfirmar(produtoCanonicoId);
    } finally {
      setSalvando(false);
    }
  }

  async function handleCriar(evento: FormEvent) {
    evento.preventDefault();
    if (!nomeNovo.trim()) {
      notificar("Informe o nome do novo produto canônico.", "erro");
      return;
    }
    setSalvando(true);
    try {
      const criado = await criarCanonico(casoId, nomeNovo.trim(), categoriaNovo.trim() || undefined);
      await queryClient.invalidateQueries({ queryKey: ["canonicos-categorias", casoId] });
      await queryClient.invalidateQueries({ queryKey: ["canonicos-busca", casoId] });
      await queryClient.invalidateQueries({ queryKey: ["canonicos-tabela", casoId] });
      // Produto já criado: seleciona e sai do modo criação. Se onConfirmar
      // falhar, o retry usa o botão principal com ele selecionado, sem tentar
      // criar de novo (o que daria 400 de nome duplicado).
      nomesConhecidos.current.set(criado.id, criado.nome_canonico);
      setSelecionadoId(criado.id);
      setCriando(false);
      await onConfirmar(criado.id);
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvando(false);
    }
  }

  const resumoBusca = busca ? ` para "${busca}"` : "";
  const resumo = `${total} ${total === 1 ? "produto encontrado" : "produtos encontrados"}${resumoBusca} em ${rotuloCategoriaAtual()}`;

  return (
    <Modal
      aberto
      onFechar={tentarFechar}
      titulo={titulo}
      tamanho="largo"
      descricao="Vincule o item da nota a um produto já cadastrado no caso ou crie um novo."
    >
      <button type="button" className={estilos.fechar} onClick={tentarFechar} aria-label="Fechar">
        ✕
      </button>

      {contexto && <div className={estilos.contexto}>{contexto}</div>}

      <div className={estilos.filtros}>
        <div className={estilos.campoBuscaWrapper}>
          <span className={estilos.iconeBusca} aria-hidden="true">
            ⌕
          </span>
          <input
            type="text"
            className={estilos.campoBusca}
            placeholder="Buscar produto canônico pelo nome..."
            aria-label="Buscar produto canônico"
            value={buscaDigitada}
            autoFocus
            onChange={(evento) => setBuscaDigitada(evento.target.value)}
          />
          {buscaDigitada && (
            <button
              type="button"
              className={estilos.limparBusca}
              aria-label="Limpar busca"
              onClick={() => {
                setBuscaDigitada("");
                setBusca("");
                setOffset(0);
              }}
            >
              ✕
            </button>
          )}
        </div>
        <select
          className={estilos.selectCategoria}
          aria-label="Filtrar por categoria"
          value={categoria}
          onChange={(evento) => mudarCategoria(evento.target.value)}
        >
          <option value="">Categoria: Todas</option>
          {listaCategorias.map((c) => (
            <option key={c} value={c}>
              Categoria: {c}
            </option>
          ))}
          <option value={SEM_CATEGORIA}>Categoria: Sem categoria</option>
        </select>
      </div>

      <div className={estilos.chips}>
        <button
          type="button"
          className={`${estilos.chip} ${categoria === "" ? estilos.chipAtivo : ""}`}
          aria-pressed={categoria === ""}
          onClick={() => mudarCategoria("")}
        >
          Todas
        </button>
        {listaCategorias.slice(0, QTD_CHIPS_CATEGORIA).map((c) => (
          <button
            key={c}
            type="button"
            className={`${estilos.chip} ${categoria === c ? estilos.chipAtivo : ""}`}
            aria-pressed={categoria === c}
            onClick={() => mudarCategoria(c)}
          >
            {c}
          </button>
        ))}
        <button
          type="button"
          className={`${estilos.chip} ${categoria === SEM_CATEGORIA ? estilos.chipAtivo : ""}`}
          aria-pressed={categoria === SEM_CATEGORIA}
          onClick={() => mudarCategoria(SEM_CATEGORIA)}
        >
          Sem categoria
        </button>
      </div>

      <p className={estilos.resumo} aria-live="polite">
        {canonicos.isError ? "Erro ao carregar os produtos canônicos." : resumo}
      </p>

      <div className={estilos.lista}>
        <div className={`${estilos.linha} ${estilos.cabecalhoLista}`}>
          <span />
          <span>NOME CANÔNICO</span>
          <span>CATEGORIA</span>
          <span>ITENS VINCULADOS</span>
        </div>
        {canonicos.isError ? (
          <div className={estilos.vazio}>
            <p className={estilos.vazioTitulo}>Não foi possível carregar os produtos canônicos.</p>
          </div>
        ) : canonicos.isLoading ? (
          <div className={estilos.vazio}>
            <p className={estilos.vazioTitulo}>Carregando...</p>
          </div>
        ) : itens.length === 0 ? (
          <div className={estilos.vazio}>
            <p className={estilos.vazioTitulo}>Nenhum produto encontrado</p>
            {permitirCriar && (
              <Botao type="button" variante="secundario" onClick={() => abrirCriacao(buscaDigitada.trim())}>
                {buscaDigitada.trim() ? `Criar "${buscaDigitada.trim()}" como novo produto` : "Criar novo produto"}
              </Botao>
            )}
          </div>
        ) : (
          <div className={estilos.corpoLista} role="radiogroup" aria-label="Produtos canônicos">
            {itens.map((canonico: ProdutoCanonico) => {
              const selecionado = canonico.id === selecionadoId;
              return (
                <label
                  key={canonico.id}
                  className={`${estilos.linha} ${estilos.linhaItem} ${selecionado ? estilos.linhaSelecionada : ""}`}
                >
                  <input
                    type="radio"
                    name="produto-canonico"
                    checked={selecionado}
                    onChange={() => setSelecionadoId(canonico.id)}
                  />
                  <span className={estilos.nome}>
                    {destacarTrecho(canonico.nome_canonico, busca)}
                    {canonico.id === idDestacado && <span className={estilos.etiquetaIa}>Sugestão da IA</span>}
                  </span>
                  <span>
                    {canonico.categoria ? (
                      <span className={estilos.pilulaCategoria}>{canonico.categoria}</span>
                    ) : (
                      "-"
                    )}
                  </span>
                  <span className={estilos.contagem}>
                    {canonico.itens_vinculados_count} {canonico.itens_vinculados_count === 1 ? "item" : "itens"}
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      <Paginacao offset={offset} limite={LIMITE_POR_PAGINA} total={total} onMudar={setOffset} />

      {criando && (
        <form onSubmit={handleCriar} className={estilos.formCriar}>
          <CampoTexto
            rotulo="Nome canônico"
            value={nomeNovo}
            onChange={(evento) => setNomeNovo(evento.target.value)}
            required
            autoFocus
          />
          <SeletorCategoria
            rotulo="Categoria"
            valor={categoriaNovo}
            categoriasExistentes={listaCategorias}
            onMudar={setCategoriaNovo}
          />
          <div className={estilos.acoesCriar}>
            <Botao type="button" variante="secundario" onClick={() => setCriando(false)} disabled={salvando}>
              Voltar
            </Botao>
            <Botao type="submit" disabled={salvando}>
              {salvando ? "Salvando..." : `Criar e ${rotuloConfirmar.toLowerCase()}`}
            </Botao>
          </div>
        </form>
      )}

      <div className={estilos.rodape}>
        {permitirCriar && !criando ? (
          <button type="button" className={estilos.botaoCriar} onClick={() => abrirCriacao()}>
            + Criar novo produto canônico
          </button>
        ) : (
          <span />
        )}
        <div className={estilos.rodapeDireita}>
          <span className={estilos.selecionadoTexto}>
            {selecionadoId !== null ? (
              <>
                Selecionado: <strong>{nomeSelecionado ?? `#${selecionadoId}`}</strong>
              </>
            ) : (
              "Nenhum produto selecionado"
            )}
          </span>
          <Botao type="button" variante="secundario" onClick={onFechar} disabled={salvando}>
            Cancelar
          </Botao>
          <Botao
            type="button"
            disabled={salvando || selecionadoId === null}
            onClick={() => selecionadoId !== null && confirmar(selecionadoId)}
          >
            {salvando ? "Salvando..." : rotuloConfirmar}
          </Botao>
        </div>
      </div>
    </Modal>
  );
}
