import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { atualizarPerfil, alterarSenha, login } from "../../api/auth";
import { editarUsuario, listarUsuarios } from "../../api/usuarios";
import { ErroApi } from "../../api/cliente";
import type { RoleUsuario, StatusCadastro, UsuarioAdmin } from "../../api/tipos";
import { useAuth } from "../../auth/ContextoAuth";
import { Badge, type StatusBadge } from "../../componentes/Badge";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import { Modal } from "../../componentes/Modal";
import { Paginacao } from "../../componentes/Paginacao";
import { Select } from "../../componentes/Select";
import { Tabela, type ColunaTabela } from "../../componentes/Tabela";
import { useToast } from "../../componentes/Toast";
import estilos from "./Configuracoes.module.css";

type Aba = "perfil" | "usuarios";

const STATUS_PARA_BADGE: Record<StatusCadastro, StatusBadge> = {
  pendente: "pendente",
  aprovado: "sucesso",
  reprovado: "erro",
};

const STATUS_PARA_ROTULO: Record<StatusCadastro, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  reprovado: "Reprovado",
};

const OPCOES_ROLE: { valor: RoleUsuario | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Todos os papéis" },
  { valor: "administrador", rotulo: "Administrador" },
  { valor: "comum", rotulo: "Comum" },
];

const OPCOES_STATUS: { valor: StatusCadastro | ""; rotulo: string }[] = [
  { valor: "", rotulo: "Todos os status" },
  { valor: "pendente", rotulo: "Pendente" },
  { valor: "aprovado", rotulo: "Aprovado" },
  { valor: "reprovado", rotulo: "Reprovado" },
];

const LIMITE_USUARIOS = 20;

export function Configuracoes() {
  const { usuario } = useAuth();
  const ehAdmin = usuario?.role === "administrador";
  const [aba, setAba] = useState<Aba>("perfil");

  return (
    <div className={estilos.pagina}>
      <div className={estilos.cabecalho}>
        <h1 className={estilos.titulo}>Configurações</h1>
        <p className={estilos.subtitulo}>Gerencie sua conta e os usuários do escritório</p>
      </div>

      <div className={estilos.tabs}>
        <button
          type="button"
          className={`${estilos.tab} ${aba === "perfil" ? estilos.tabAtiva : ""}`}
          onClick={() => setAba("perfil")}
        >
          Perfil
        </button>
        {ehAdmin && (
          <button
            type="button"
            className={`${estilos.tab} ${aba === "usuarios" ? estilos.tabAtiva : ""}`}
            onClick={() => setAba("usuarios")}
          >
            Usuários
          </button>
        )}
      </div>

      {aba === "usuarios" && ehAdmin ? <AbaUsuarios /> : <AbaPerfil />}
    </div>
  );
}

function AbaPerfil() {
  const { usuario: usuarioLogado, sair, atualizarUsuario } = useAuth();
  const navigate = useNavigate();
  const { notificar } = useToast();

  const [nome, setNome] = useState(usuarioLogado?.nome ?? "");
  const [email, setEmail] = useState(usuarioLogado?.email ?? "");
  const [salvandoPerfil, setSalvandoPerfil] = useState(false);

  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [alterandoSenha, setAlterandoSenha] = useState(false);

  if (!usuarioLogado) return null;
  const usuario = usuarioLogado;

  async function handleSalvarPerfil(evento: FormEvent) {
    evento.preventDefault();
    setSalvandoPerfil(true);
    try {
      const atualizado = await atualizarPerfil({ nome: nome.trim(), email: email.trim() });
      atualizarUsuario(atualizado);
      notificar("Dados da conta atualizados com sucesso.", "sucesso");
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvandoPerfil(false);
    }
  }

  async function handleAlterarSenha(evento: FormEvent) {
    evento.preventDefault();
    if (novaSenha.length < 8) {
      notificar("A nova senha precisa ter no mínimo 8 caracteres.", "erro");
      return;
    }
    if (novaSenha !== confirmarSenha) {
      notificar("A confirmação não bate com a nova senha.", "erro");
      return;
    }

    setAlterandoSenha(true);
    try {
      // Confirma a senha atual reaproveitando o login (descarta o token) --
      // evita criar um endpoint só para "verificar senha".
      await login(usuario.email, senhaAtual);
      await alterarSenha(novaSenha);
      notificar("Senha alterada com sucesso.", "sucesso");
      setSenhaAtual("");
      setNovaSenha("");
      setConfirmarSenha("");
    } catch (excecao) {
      if (excecao instanceof ErroApi && excecao.status === 401) {
        notificar("Senha atual incorreta.", "erro");
      } else {
        notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
      }
    } finally {
      setAlterandoSenha(false);
    }
  }

  function handleSairDaConta() {
    sair();
    navigate("/login");
  }

  return (
    <div className={estilos.colunaFormulario}>
      <Card>
        <form onSubmit={handleSalvarPerfil} className={estilos.formCard}>
          <p className={estilos.tituloCard}>Dados da conta</p>
          <CampoTexto rotulo="Nome completo" value={nome} onChange={(e) => setNome(e.target.value)} required />
          <CampoTexto
            rotulo="E-mail"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <div className={estilos.papelAcesso}>
            <div className={estilos.papelLinha}>
              <span className={estilos.papelRotulo}>Papel de acesso</span>
              <Badge
                status={usuario.role === "administrador" ? "info" : "neutro"}
                rotulo={usuario.role === "administrador" ? "Administrador" : "Comum"}
              />
            </div>
            <p className={estilos.papelAjuda}>Só um administrador pode alterar papéis de acesso.</p>
          </div>
          <div className={estilos.rodapeCard}>
            <Botao type="submit" disabled={salvandoPerfil}>
              {salvandoPerfil ? "Salvando..." : "Salvar alterações"}
            </Botao>
          </div>
        </form>
      </Card>

      <Card>
        <form onSubmit={handleAlterarSenha} className={estilos.formCard}>
          <p className={estilos.tituloCard}>Alterar senha</p>
          <CampoTexto
            rotulo="Senha atual"
            type="password"
            value={senhaAtual}
            onChange={(e) => setSenhaAtual(e.target.value)}
            required
          />
          <CampoTexto
            rotulo="Nova senha"
            type="password"
            value={novaSenha}
            onChange={(e) => setNovaSenha(e.target.value)}
            required
          />
          <CampoTexto
            rotulo="Confirmar nova senha"
            type="password"
            value={confirmarSenha}
            onChange={(e) => setConfirmarSenha(e.target.value)}
            required
          />
          <p className={estilos.textoAjuda}>Mínimo de 8 caracteres.</p>
          <div className={estilos.rodapeCard}>
            <Botao type="submit" disabled={alterandoSenha}>
              {alterandoSenha ? "Alterando..." : "Alterar senha"}
            </Botao>
          </div>
        </form>
      </Card>

      <Card>
        <div className={estilos.formCard}>
          <p className={estilos.tituloCard}>Sessão</p>
          <p className={estilos.textoAjuda}>Sua sessão expira automaticamente 1 hora após o login.</p>
          <div className={estilos.rodapeCard}>
            <Botao variante="secundario" onClick={handleSairDaConta}>
              Sair da conta
            </Botao>
          </div>
        </div>
      </Card>
    </div>
  );
}

function AbaUsuarios() {
  const { notificar } = useToast();
  const queryClient = useQueryClient();

  const [roleFiltro, setRoleFiltro] = useState<RoleUsuario | "">("");
  const [statusFiltro, setStatusFiltro] = useState<StatusCadastro | "">("");
  const [buscaDigitada, setBuscaDigitada] = useState("");
  const [busca, setBusca] = useState("");
  const [offset, setOffset] = useState(0);
  const [editandoPapel, setEditandoPapel] = useState<UsuarioAdmin | null>(null);

  useEffect(() => {
    const temporizador = setTimeout(() => setBusca(buscaDigitada), 400);
    return () => clearTimeout(temporizador);
  }, [buscaDigitada]);

  const usuarios = useQuery({
    queryKey: ["usuarios", roleFiltro, statusFiltro, busca, offset],
    queryFn: () =>
      listarUsuarios({
        role: roleFiltro || undefined,
        statusCadastro: statusFiltro || undefined,
        busca: busca || undefined,
        limit: LIMITE_USUARIOS,
        offset,
      }),
  });

  async function invalidar() {
    await queryClient.invalidateQueries({ queryKey: ["usuarios"] });
  }

  async function handleToggleAtivo(alvo: UsuarioAdmin) {
    try {
      await editarUsuario(alvo.id, { isActive: !alvo.is_active });
      notificar(`Usuário ${alvo.is_active ? "desativado" : "ativado"} com sucesso.`, "sucesso");
      await invalidar();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    }
  }

  const colunas: ColunaTabela<UsuarioAdmin>[] = [
    { chave: "nome", titulo: "Nome", renderizar: (u) => u.nome },
    { chave: "email", titulo: "E-mail", renderizar: (u) => u.email },
    {
      chave: "role",
      titulo: "Papel",
      renderizar: (u) => (
        <Badge status={u.role === "administrador" ? "info" : "neutro"} rotulo={u.role === "administrador" ? "Administrador" : "Comum"} />
      ),
    },
    {
      chave: "status_cadastro",
      titulo: "Status",
      renderizar: (u) => (
        <span className={estilos.statusCelula}>
          <Badge status={STATUS_PARA_BADGE[u.status_cadastro]} rotulo={STATUS_PARA_ROTULO[u.status_cadastro]} />
          {!u.is_active && <Badge status="erro" rotulo="Inativo" />}
        </span>
      ),
    },
    {
      chave: "criado_em",
      titulo: "Cadastrado em",
      renderizar: (u) => new Date(u.criado_em).toLocaleDateString("pt-BR"),
    },
    {
      chave: "acoes",
      titulo: "Ações",
      renderizar: (u) => (
        <div className={estilos.acoes}>
          <button
            type="button"
            className={estilos.acaoNeutra}
            title="Alterar papel de acesso"
            onClick={() => setEditandoPapel(u)}
          >
            ✎
          </button>
          <button
            type="button"
            className={estilos.acaoNeutra}
            title={u.is_active ? "Desativar usuário" : "Ativar usuário"}
            onClick={() => handleToggleAtivo(u)}
          >
            {u.is_active ? "⊘" : "✓"}
          </button>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className={estilos.barraFiltros}>
        <div className={estilos.filtros}>
          <Select
            valor={roleFiltro}
            opcoes={OPCOES_ROLE}
            onMudar={(valor) => {
              setRoleFiltro(valor);
              setOffset(0);
            }}
            rotuloAria="Filtrar por papel"
          />
          <Select
            valor={statusFiltro}
            opcoes={OPCOES_STATUS}
            onMudar={(valor) => {
              setStatusFiltro(valor);
              setOffset(0);
            }}
            rotuloAria="Filtrar por status"
          />
        </div>
        <input
          type="search"
          className={estilos.campoBusca}
          placeholder="Buscar por nome ou e-mail"
          value={buscaDigitada}
          onChange={(evento) => {
            setBuscaDigitada(evento.target.value);
            setOffset(0);
          }}
        />
      </div>

      <Card>
        <Tabela
          colunas={colunas}
          linhas={usuarios.data?.itens ?? []}
          chaveLinha={(linha) => linha.id}
          vazio="Nenhum usuário encontrado com esses filtros."
        />
        {usuarios.data && (
          <Paginacao offset={offset} limite={LIMITE_USUARIOS} total={usuarios.data.total} onMudar={setOffset} />
        )}
      </Card>

      {editandoPapel && (
        <ModalAlterarPapel
          usuario={editandoPapel}
          onFechar={() => setEditandoPapel(null)}
          onSalvo={async () => {
            setEditandoPapel(null);
            notificar("Papel de acesso alterado com sucesso.", "sucesso");
            await invalidar();
          }}
        />
      )}
    </>
  );
}

interface ModalAlterarPapelProps {
  usuario: UsuarioAdmin;
  onFechar: () => void;
  onSalvo: () => void;
}

function ModalAlterarPapel({ usuario, onFechar, onSalvo }: ModalAlterarPapelProps) {
  const { notificar } = useToast();
  const [papel, setPapel] = useState<RoleUsuario>(usuario.role);
  const [salvando, setSalvando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    try {
      await editarUsuario(usuario.id, { role: papel });
      onSalvo();
    } catch (excecao) {
      notificar(excecao instanceof ErroApi ? excecao.message : "Erro de comunicação com a API.", "erro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal aberto onFechar={onFechar} titulo="Alterar papel de acesso">
      <form onSubmit={handleSubmit} className={estilos.formModal}>
        <p className={estilos.nomeUsuarioModal}>{usuario.nome}</p>
        <select
          className={estilos.selectNativo}
          value={papel}
          onChange={(evento) => setPapel(evento.target.value as RoleUsuario)}
        >
          <option value="comum">Comum</option>
          <option value="administrador">Administrador</option>
        </select>
        <p className={estilos.textoAjuda}>Esta alteração é registrada no log de auditoria.</p>
        <div className={estilos.acoesModal}>
          <Botao type="button" variante="secundario" onClick={onFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" disabled={salvando}>
            {salvando ? "Salvando..." : "Confirmar"}
          </Botao>
        </div>
      </form>
    </Modal>
  );
}
