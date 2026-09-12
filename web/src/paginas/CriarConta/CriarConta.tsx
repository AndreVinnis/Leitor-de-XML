import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { criarConta } from "../../api/auth";
import { ErroApi } from "../../api/cliente";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import estilos from "./CriarConta.module.css";

export function CriarConta() {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [cadastroEnviado, setCadastroEnviado] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setErro(null);

    if (senha !== confirmarSenha) {
      setErro("As senhas não coincidem.");
      return;
    }

    setEnviando(true);
    try {
      await criarConta(nome, email, senha);
      setCadastroEnviado(true);
    } catch (excecao) {
      if (excecao instanceof ErroApi && excecao.status === 400 && excecao.message.includes("REGISTER_USER_ALREADY_EXISTS")) {
        setErro("Esse e-mail já está cadastrado.");
      } else if (excecao instanceof ErroApi && excecao.status === 422) {
        setErro("Verifique se o e-mail é válido e a senha tem pelo menos 8 caracteres.");
      } else {
        setErro("Não foi possível criar a conta. Tente novamente em alguns instantes.");
      }
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className={estilos.pagina}>
      <aside className={estilos.painelMarca}>
        <div className={estilos.logoCirculo} />
        <h1 className={estilos.tituloMarca}>Leitor de XML</h1>
        <p className={estilos.descricaoMarca}>
          Crie sua conta gratuita e comece a organizar suas notas fiscais eletrônicas em minutos.
        </p>
        <div className={estilos.linhaDestaque} />
      </aside>

      <div className={estilos.painelFormulario}>
        <Card className={estilos.cartao}>
          <h2 className={estilos.titulo}>Criar conta</h2>

          {cadastroEnviado ? (
            <>
              <p className={estilos.mensagemSucesso}>
                Cadastro enviado. Você vai receber um e-mail assim que um administrador aprovar o seu acesso.
              </p>
              <p className={estilos.linhaEntrar}>
                <Link to="/login" className={estilos.linkEntrar}>
                  Voltar para o login
                </Link>
              </p>
            </>
          ) : (
            <>
              <p className={estilos.subtitulo}>Preencha os dados para começar a usar o Leitor de XML</p>

              <form onSubmit={handleSubmit} className={estilos.formulario}>
                <CampoTexto
                  rotulo="Nome completo"
                  name="nome"
                  placeholder="Seu nome"
                  autoComplete="name"
                  value={nome}
                  onChange={(evento) => setNome(evento.target.value)}
                  required
                />
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
                  autoComplete="new-password"
                  minLength={8}
                  value={senha}
                  onChange={(evento) => setSenha(evento.target.value)}
                  required
                />
                <CampoTexto
                  rotulo="Confirmar senha"
                  type="password"
                  name="confirmarSenha"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  minLength={8}
                  value={confirmarSenha}
                  onChange={(evento) => setConfirmarSenha(evento.target.value)}
                  required
                />

                {erro && <p className={estilos.mensagemErro}>{erro}</p>}

                <Botao type="submit" disabled={enviando}>
                  {enviando ? "Criando conta..." : "Criar conta"}
                </Botao>
              </form>

              <p className={estilos.linhaEntrar}>
                Já tem uma conta?{" "}
                <Link to="/login" className={estilos.linkEntrar}>
                  Entrar
                </Link>
              </p>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
