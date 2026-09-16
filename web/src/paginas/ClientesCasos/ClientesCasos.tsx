import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { atualizarCaso, criarCaso, excluirCaso, listarCasos } from "../../api/casos";
import { ErroApi } from "../../api/cliente";
import type { ClienteCaso } from "../../api/tipos";
import { useAuth } from "../../auth/ContextoAuth";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import { Modal } from "../../componentes/Modal";
import { Paginacao } from "../../componentes/Paginacao";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { useToast } from "../../componentes/Toast";
import { formatarCnpj } from "../../utilitarios/formatarCnpj";
import estilos from "./ClientesCasos.module.css";

const LIMITE = 10;

export function ClientesCasos() {
  const { usuario } = useAuth();
  const queryClient = useQueryClient();
  const { notificar } = useToast();
  const ehAdministrador = usuario?.role === "administrador";

  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);
  const [editando, setEditando] = useState<ClienteCaso | null>(null);
  const [excluindo, setExcluindo] = useState<ClienteCaso | null>(null);
  const [criando, setCriando] = useState(false);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  // GET /api/casos não pagina nem filtra no backend -- mesma queryKey que
  // ContextoCaso.tsx usa para o seletor da topbar, então invalidar ["casos"]
  // depois de editar/excluir atualiza os dois lugares de graça.
  const casos = useQuery({ queryKey: ["casos"], queryFn: listarCasos });

  const casosFiltrados = useMemo(() => {
    const alvo = busca.trim().toLowerCase();
    const todos = casos.data ?? [];
    if (!alvo) return todos;
    return todos.filter((caso) => {
      const texto = `${caso.nome_cliente} ${caso.identificacao_caso ?? ""} ${caso.cnpj_cliente ?? ""}`.toLowerCase();
      return texto.includes(alvo);
    });
  }, [casos.data, busca]);

  const casosPagina = casosFiltrados.slice(offset, offset + LIMITE);

  function resetarPagina() {
    setOffset(0);
  }

  async function invalidarCasos() {
    await queryClient.invalidateQueries({ queryKey: ["casos"] });
  }

  const colunas: ColunaTabela<ClienteCaso>[] = [
    { chave: "nome_cliente", titulo: "Nome do Cliente", renderizar: (c) => c.nome_cliente },
    {
      chave: "identificacao_caso",
      titulo: "Identificação do Caso",
      renderizar: (c) => c.identificacao_caso || "-",
    },
    { chave: "cnpj_cliente", titulo: "CNPJ", renderizar: (c) => formatarCnpj(c.cnpj_cliente) || "-" },
    {
      chave: "criado_em",
      titulo: "Criado em",
      renderizar: (c) => new Date(c.criado_em).toLocaleDateString("pt-BR"),
    },
    {
      chave: "acoes",
      titulo: "Ações",
      renderizar: (caso) => (
        <div className={estilos.acoes}>
          <button
            type="button"
            className={estilos.acaoNeutra}
            title="Editar cliente/caso"
            onClick={() => setEditando(caso)}
          >
            ✎
          </button>
          {ehAdministrador && (
            <button
              type="button"
              className={estilos.acaoErro}
              title="Excluir cliente/caso"
              onClick={() => setExcluindo(caso)}
            >
              ✕
            </button>
          )}
        </div>
      ),
    },
  ];

  async function confirmarExclusao(casoId: number) {
    try {
      await excluirCaso(casoId);
      notificar("Cliente/caso excluído com sucesso.", "sucesso");
      setExcluindo(null);
      await invalidarCasos();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Clientes e Casos</h1>
        <p className={estilos.subtitulo}>
          Cadastre, edite ou exclua um cliente/caso.
        </p>
      </div>

      <div className={estilos.barraFiltros}>
        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar por nome ou identificação do caso..."
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            resetarPagina();
          }}
        />
        <Botao type="button" onClick={() => setCriando(true)}>
          + Novo cliente/caso
        </Botao>
      </div>

      <Card>
        <Tabela
          colunas={colunas}
          linhas={casosPagina}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhum cliente/caso encontrado com esses filtros."
        />
        <Paginacao offset={offset} limite={LIMITE} total={casosFiltrados.length} onMudar={setOffset} />
      </Card>

      {criando && (
        <ModalCriarClienteCaso
          onFechar={() => setCriando(false)}
          onSalvo={async () => {
            setCriando(false);
            await invalidarCasos();
            notificar("Cliente/caso criado com sucesso.", "sucesso");
          }}
        />
      )}

      {editando && (
        <ModalEditarClienteCaso
          caso={editando}
          onFechar={() => setEditando(null)}
          onSalvo={async () => {
            setEditando(null);
            await invalidarCasos();
            notificar("Cliente/caso atualizado com sucesso.", "sucesso");
          }}
        />
      )}

      {excluindo && (
        <Modal aberto onFechar={() => setExcluindo(null)} titulo="Excluir cliente/caso?">
          <div className={estilos.formModal}>
            <p className={estilos.nomeClienteModal}>
              {excluindo.nome_cliente}
              {excluindo.identificacao_caso ? ` · ${excluindo.identificacao_caso}` : ""}
            </p>
            <p className={estilos.textoAjuda}>
              Esta ação é permanente e não pode ser desfeita. Todas as notas fiscais, itens vinculados, sugestões de
              normalização e produtos canônicos deste cliente/caso serão excluídos.
            </p>
            <div className={estilos.acoesModal}>
              <Botao type="button" variante="secundario" onClick={() => setExcluindo(null)}>
                Cancelar
              </Botao>
              <Botao type="button" className={estilos.botaoExcluir} onClick={() => confirmarExclusao(excluindo.id)}>
                Excluir permanentemente
              </Botao>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

interface ModalCriarClienteCasoProps {
  onFechar: () => void;
  onSalvo: () => void;
}

function ModalCriarClienteCaso({ onFechar, onSalvo }: ModalCriarClienteCasoProps) {
  const { notificar } = useToast();
  const [nome, setNome] = useState("");
  const [identificacao, setIdentificacao] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [salvando, setSalvando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    if (!nome.trim() || !cnpj.trim()) return;
    setSalvando(true);
    try {
      await criarCaso(nome.trim(), cnpj.trim(), identificacao.trim() || undefined);
      onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal aberto onFechar={onFechar} titulo="Novo cliente/caso">
      <form onSubmit={handleSubmit} className={estilos.formModal}>
        <CampoTexto
          rotulo="Nome do cliente"
          placeholder="Digite o nome do cliente"
          autoFocus
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          required
        />
        <CampoTexto
          rotulo="Identificação do caso"
          placeholder="Ex.: Proc. 1234"
          value={identificacao}
          onChange={(evento) => setIdentificacao(evento.target.value)}
        />
        <CampoTexto
          rotulo="CNPJ"
          placeholder="00.000.000/0000-00"
          value={cnpj}
          onChange={(evento) => setCnpj(evento.target.value)}
          required
        />
        <div className={estilos.acoesModal}>
          <Botao type="button" variante="secundario" onClick={onFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" disabled={salvando}>
            {salvando ? "Criando..." : "Criar cliente/caso"}
          </Botao>
        </div>
      </form>
    </Modal>
  );
}

interface ModalEditarClienteCasoProps {
  caso: ClienteCaso;
  onFechar: () => void;
  onSalvo: () => void;
}

function ModalEditarClienteCaso({ caso, onFechar, onSalvo }: ModalEditarClienteCasoProps) {
  const { notificar } = useToast();
  const [nome, setNome] = useState(caso.nome_cliente);
  const [identificacao, setIdentificacao] = useState(caso.identificacao_caso ?? "");
  const [salvando, setSalvando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    if (!nome.trim()) return;
    setSalvando(true);
    try {
      // cnpj_cliente nunca é enviado aqui -- o campo é somente leitura nesta
      // tela, e o backend rejeita com 422 qualquer tentativa de trocar um
      // CNPJ já definido.
      await atualizarCaso(caso.id, {
        nome_cliente: nome.trim(),
        identificacao_caso: identificacao.trim() || null,
      });
      onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal aberto onFechar={onFechar} titulo="Editar cliente/caso">
      <form onSubmit={handleSubmit} className={estilos.formModal}>
        <CampoTexto
          rotulo="Nome do cliente"
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          required
        />
        <CampoTexto
          rotulo="Identificação do caso"
          value={identificacao}
          onChange={(evento) => setIdentificacao(evento.target.value)}
        />
        <CampoTexto rotulo="CNPJ" value={formatarCnpj(caso.cnpj_cliente)} disabled readOnly />
        <p className={estilos.textoAjuda}>O CNPJ não pode ser alterado após o cadastro.</p>
        <div className={estilos.acoesModal}>
          <Botao type="button" variante="secundario" onClick={onFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" disabled={salvando}>
            {salvando ? "Salvando..." : "Salvar alterações"}
          </Botao>
        </div>
      </form>
    </Modal>
  );
}
