"""
Cria o primeiro usuário administrador direto no banco, já aprovado.

Necessário porque, no fluxo normal, só um administrador já aprovado pode
aprovar novos cadastros -- alguém precisa existir antes desse ciclo começar.

Uso:
    docker compose exec api python -m app.scripts.criar_admin --nome "Ana" --email ana@escritorio.com
"""

import argparse
import getpass

from fastapi_users.password import PasswordHelper

from app.core.auth import TAMANHO_MINIMO_SENHA
from app.core.database import SessionLocal
from app.models.models import RoleUsuario, StatusCadastro, Usuario


def criar_admin(nome: str, email: str, senha: str) -> None:
    db = SessionLocal()
    try:
        existente = db.query(Usuario).filter_by(email=email).first()
        if existente:
            raise SystemExit(f"Já existe um usuário com o e-mail {email}.")

        password_helper = PasswordHelper()
        usuario = Usuario(
            nome=nome,
            email=email,
            hashed_password=password_helper.hash(senha),
            role=RoleUsuario.ADMINISTRADOR,
            status_cadastro=StatusCadastro.APROVADO,
            is_active=True,
            is_superuser=True,
            is_verified=True,
        )
        db.add(usuario)
        db.commit()
        print(f"Administrador {email} criado com sucesso.")
    finally:
        db.close()


def email_contido(email: str, senha: str) -> bool:
    return email.lower() in senha.lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria o primeiro usuário administrador.")
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    senha = getpass.getpass("Senha do administrador: ")
    confirmacao = getpass.getpass("Confirme a senha: ")
    if senha != confirmacao:
        raise SystemExit("As senhas não coincidem.")
    # Mesma regra do UserManager.validate_password (app/core/auth.py), que
    # este script não passa por usar o PasswordHelper direto.
    if len(senha) < TAMANHO_MINIMO_SENHA or email_contido(args.email, senha):
        raise SystemExit(
            f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres "
            "e não pode conter o e-mail."
        )

    criar_admin(args.nome, args.email, senha)


if __name__ == "__main__":
    main()
