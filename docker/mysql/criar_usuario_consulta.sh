#!/bin/sh
# Cria (ou atualiza) o usuário MySQL somente leitura do NL->SQL.
#
# É a segunda camada de defesa da tela de Consulta: o SQL gerado pela IA já
# passa por app/core/sql_seguranca.py, e ainda assim roda com um usuário que
# só tem SELECT em notas, itens_nota e produtos_canonicos. Se o validador
# deixar passar algo, o banco recusa.
#
# Roda DEPOIS do `alembic upgrade head` (o MySQL não aceita GRANT em tabela
# que ainda não existe), dentro do container do banco:
#
#   docker compose exec db sh /scripts/criar_usuario_consulta.sh
#
# Idempotente: pode rodar de novo para trocar a senha. Lê do ambiente do
# container: MYSQL_ROOT_PASSWORD, MYSQL_DATABASE e MYSQL_CONSULTA_PASSWORD.
set -eu

: "${MYSQL_CONSULTA_PASSWORD:?defina MYSQL_CONSULTA_PASSWORD no .env}"
BANCO="${MYSQL_DATABASE:-nfe_sistema}"

# A senha entra num literal SQL abaixo. Aspas simples quebrariam o comando,
# e a barra invertida o MySQL interpreta como escape (gravaria uma senha
# diferente da do .env, sem erro nenhum). Mais simples recusar as duas.
case "$MYSQL_CONSULTA_PASSWORD" in
  *\'*|*\\*)
    echo "MYSQL_CONSULTA_PASSWORD não pode conter aspas simples nem barra invertida." >&2
    exit 1
    ;;
esac

# Senha do root por variável de ambiente, não por -p na linha de comando
# (que fica visível no `ps` de dentro do container).
export MYSQL_PWD="${MYSQL_ROOT_PASSWORD}"

mysql -uroot <<SQL
CREATE USER IF NOT EXISTS 'nfe_consulta'@'%' IDENTIFIED BY '${MYSQL_CONSULTA_PASSWORD}';
ALTER USER 'nfe_consulta'@'%' IDENTIFIED BY '${MYSQL_CONSULTA_PASSWORD}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'nfe_consulta'@'%';
GRANT SELECT ON \`${BANCO}\`.notas TO 'nfe_consulta'@'%';
GRANT SELECT ON \`${BANCO}\`.itens_nota TO 'nfe_consulta'@'%';
GRANT SELECT ON \`${BANCO}\`.produtos_canonicos TO 'nfe_consulta'@'%';
FLUSH PRIVILEGES;
SQL

echo "Usuário nfe_consulta pronto (SELECT em notas, itens_nota, produtos_canonicos de ${BANCO})."
echo "No .env da API: DATABASE_URL_CONSULTA=mysql+pymysql://nfe_consulta:<senha>@db:3306/${BANCO}"
echo "(caracteres como @ : / % na senha precisam ir URL-encoded nessa URL)"
