import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { redefinirSenha } from "../../api/auth";
import { ErroApi } from "../../api/cliente";
import { Botao } from "../../componentes/Botao";
import { CampoTexto } from "../../componentes/CampoTexto";
import { Card } from "../../componentes/Card";
import estilos from "./RedefinirSenha.module.css";

export function RedefinirSenha() {
  const [parametros] = useSearchParams();
  const token = parametros.get("token");

  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarSenha, setConfirmarSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [redefinicaoConcluida, setRedefinicaoConcluida] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setErro(null);

    if (!token) return;

    if (novaSenha.length < 8) {
      setErro("A nova senha precisa ter no mínimo 8 caracteres.");
      return;
    }
    if (novaSenha !== confirmarSenha) {
      setErro("As senhas não coincidem.");
      return;
    }

    setEnviando(true);
    try {
      await redefinirSenha(token, novaSenha);
      setRedefinicaoConcluida(true);
    } catch (excecao) {
      if (excecao instanceof ErroApi && excecao.status === 400 && excecao.message.includes("RESET_PASSWORD_BAD_TOKEN")) {
        setErro("Este link expirou ou já foi usado. Solicite uma nova redefinição na tela de login.");
      } else if (excecao instanceof ErroApi && excecao.status === 400 && excecao.message.includes("RESET_PASSWORD_INVALID_PASSWORD")) {
        setErro("A senha não atende aos requisitos mínimos.");
      } else {
        setErro("Não foi possível redefinir a senha. Tente novamente em alguns instantes.");
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
          Leitura, validação e organização inteligente das suas notas fiscais eletrônicas (NF-e), em um só lugar.
        </p>
        <div className={estilos.linhaDestaque} />
      </aside>

      <div className={estilos.painelFormulario}>
        <Card className={estilos.cartao}>
          <h2 className={estilos.titulo}>Redefinir senha</h2>

          {!token ? (
            <p className={estilos.mensagemErro}>
              Link inválido ou incompleto. Solicite uma nova redefinição na tela de login.
            </p>
          ) : redefinicaoConcluida ? (
            <>
              <p className={estilos.mensagemSucesso}>Sua senha foi redefinida com sucesso.</p>
              <p className={estilos.linhaEntrar}>
                <Link to="/login" className={estilos.linkEntrar}>
                  Ir para o login
                </Link>
              </p>
            </>
          ) : (
            <>
              <p className={estilos.subtitulo}>Escolha uma nova senha para acessar sua conta</p>

              <form onSubmit={handleSubmit} className={estilos.formulario}>
                <CampoTexto
                  rotulo="Nova senha"
                  type="password"
                  name="novaSenha"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  minLength={8}
                  value={novaSenha}
                  onChange={(evento) => setNovaSenha(evento.target.value)}
                  required
                />
                <CampoTexto
                  rotulo="Confirmar nova senha"
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
                  {enviando ? "Redefinindo..." : "Redefinir senha"}
                </Botao>
              </form>

              <p className={estilos.linhaEntrar}>
                Lembrou a senha?{" "}
                <Link to="/login" className={estilos.linkEntrar}>
                  Voltar para o login
                </Link>
              </p>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
