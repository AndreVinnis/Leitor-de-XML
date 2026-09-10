import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/ContextoAuth";
import { solicitarRedefinicaoSenha } from "../../api/auth";
import { ErroApi } from "../../api/cliente";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import estilos from "./Login.module.css";

export function Login() {
  const { entrar, carregando } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  const [mostrarRecuperacao, setMostrarRecuperacao] = useState(false);
  const [emailRecuperacao, setEmailRecuperacao] = useState("");
  const [enviandoRecuperacao, setEnviandoRecuperacao] = useState(false);
  const [recuperacaoEnviada, setRecuperacaoEnviada] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setErro(null);
    try {
      await entrar(email, senha);
      navigate("/", { replace: true });
    } catch (excecao) {
      if (excecao instanceof ErroApi && excecao.status === 400) {
        // LOGIN_BAD_CREDENTIALS cobre tanto senha errada quanto cadastro
        // ainda pendente de aprovação (on_after_register força
        // is_active=False) -- as duas causas são indistinguíveis pela API.
        setErro("E-mail ou senha incorretos, ou o cadastro ainda está pendente de aprovação por um administrador.");
      } else {
        setErro("Não foi possível entrar. Tente novamente em alguns instantes.");
      }
    }
  }

  async function handleRecuperacao(evento: FormEvent) {
    evento.preventDefault();
    setEnviandoRecuperacao(true);
    try {
      await solicitarRedefinicaoSenha(emailRecuperacao);
    } finally {
      // A API sempre responde 202, exista ou não o e-mail -- a mensagem de
      // sucesso é fixa e não revela se o e-mail está cadastrado.
      setEnviandoRecuperacao(false);
      setRecuperacaoEnviada(true);
    }
  }

  return (
    <div className={estilos.pagina}>
      <aside className={estilos.painelMarca}>
        <div className={estilos.logoCirculo} />
        <h1 className={estilos.tituloMarca}>Leitor de XML</h1>
        <p className={estilos.descricaoMarca}>
          Leitura, validação e organização inteligente das suas notas fiscais eletrônicas (NF-e), em um só lugar.
        </p>
        <div className={estilos.linhaDestaque} />
      </aside>

      <div className={estilos.painelFormulario}>
        <Card className={estilos.cartao}>
          <h2 className={estilos.titulo}>Bem-vindo de volta</h2>
          <p className={estilos.subtitulo}>Acesse sua conta para continuar</p>

          <form onSubmit={handleSubmit} className={estilos.formulario}>
            <CampoTexto
              rotulo="E-mail"
              type="email"
              name="email"
              placeholder="seu@email.com"
              autoComplete="email"
              value={email}
              onChange={(evento) => setEmail(evento.target.value)}
              required
            />
            <CampoTexto
              rotulo="Senha"
              type="password"
              name="senha"
              placeholder="••••••••"
              autoComplete="current-password"
              value={senha}
              onChange={(evento) => setSenha(evento.target.value)}
              required
            />

            <div className={estilos.linhaRecuperacao}>
              <button type="button" className={estilos.linkRecuperacao} onClick={() => setMostrarRecuperacao((atual) => !atual)}>
                Esqueci minha senha
              </button>
            </div>

            {erro && <p className={estilos.mensagemErro}>{erro}</p>}

            <Botao type="submit" disabled={carregando}>
              {carregando ? "Entrando..." : "Entrar"}
            </Botao>
          </form>

          <p className={estilos.linhaCriarConta}>
            Não tem uma conta? <Link to="/criar-conta" className={estilos.linkCriarConta}>Criar conta</Link>
          </p>

          {mostrarRecuperacao && (
            <form onSubmit={handleRecuperacao} className={estilos.formRecuperacao}>
              {recuperacaoEnviada ? (
                <p className={estilos.mensagemSucesso}>
                  Se o e-mail informado estiver cadastrado, você vai receber um link para redefinir a senha.
                </p>
              ) : (
                <>
                  <CampoTexto
                    rotulo="E-mail para redefinição"
                    type="email"
                    value={emailRecuperacao}
                    onChange={(evento) => setEmailRecuperacao(evento.target.value)}
                    required
                  />
                  <Botao type="submit" variante="secundario" disabled={enviandoRecuperacao}>
                    {enviandoRecuperacao ? "Enviando..." : "Enviar link de redefinição"}
                  </Botao>
                </>
              )}
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}
