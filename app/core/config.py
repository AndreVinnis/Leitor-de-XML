from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores que já apareceram como default/exemplo (incluindo o placeholder do
# .env.example, que é público no repositório) e nunca podem assinar JWT.
_SECRET_KEYS_FRACAS = {
    "",
    "change-me",
    "changeme",
    "secret",
    "troque_por_uma_chave_secreta_longa",
}
TAMANHO_MINIMO_SECRET_KEY = 32


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://nfe_user:nfe_pass@db:3306/nfe_sistema"
    # Usuário MySQL só com SELECT nas tabelas do NL->SQL -- ver
    # app/core/database.py::SessionConsulta. Vazio = usa database_url.
    database_url_consulta: str = ""
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    gemini_api_key: str = ""
    # gemini-embedding-001 tem shutdown anunciado para 14/05/2028;
    # gemini-embedding-2 é a substituição recomendada pela Google (GA desde
    # 22/04/2026, sem shutdown anunciado). Trocar o modelo aqui exige rodar
    # `python -m app.scripts.backfill_embeddings` de novo em cada ambiente
    # (produtos canônicos com embedding_modelo antigo ficam de fora do
    # pré-filtro de similaridade até lá -- ver app/ai/embeddings.py).
    gemini_embedding_model: str = "gemini-embedding-2"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    # Assina JWT de sessão, token de redefinição de senha e links de
    # aprovação de cadastro. Sem default de propósito: a API e o worker não
    # sobem sem uma chave forte no .env (ver _validar_secret_key abaixo).
    secret_key: str = ""

    api_base_url: str = "http://localhost:8000"
    # Origem do frontend React (web/), usada para montar links enviados por
    # e-mail que apontam para telas do app (ex.: redefinição de senha) --
    # api_base_url aponta para o backend, não serve para isso.
    frontend_base_url: str = "http://localhost:5173"
    token_aprovacao_expira_minutos: int = 30

    # Origens autorizadas a chamar a API pelo browser (CORS). Lista separada
    # por vírgula -- o Streamlit não precisa disso (chama a API do lado do
    # servidor), mas o frontend React em web/ roda no browser do host.
    cors_origins: str = "http://localhost:5173"

    # Cookie de sessão do frontend React (CookieTransport em app/core/auth.py).
    # cookie_secure só é True atrás de https -- em dev http (mesmo com proxy
    # same-origin) o browser descarta um cookie Secure sem avisar, e todo
    # request autenticado vira 401 silencioso. Nunca ligar por default
    # implícito, só via .env quando o ambiente for https de verdade.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_max_age_segundos: int = 3600

    # Tetos do upload de XML (app/api/routes_upload.py). Uma NF-e real fica
    # na casa das dezenas de KB; 5 MB por arquivo é folga, não meta.
    upload_max_bytes_por_arquivo: int = 5 * 1024 * 1024
    upload_max_bytes_por_lote: int = 500 * 1024 * 1024

    # Limite de tentativas (app/core/limite_taxa.py). Login e esqueci-a-senha
    # contam por e-mail e por IP; consulta e normalização, por usuário.
    limite_login_por_email: int = 10  # por 15 min
    limite_login_por_ip: int = 50  # por 15 min
    limite_esqueci_senha_por_email: int = 3  # por hora
    limite_esqueci_senha_por_ip: int = 20  # por hora
    limite_cadastro_por_ip: int = 10  # por hora
    limite_consulta_por_minuto: int = 20
    limite_consulta_por_dia: int = 300
    limite_normalizacao_por_hora: int = 10

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    email_from: str = "no-reply@leitorxml.local"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("secret_key")
    @classmethod
    def _validar_secret_key(cls, valor: str) -> str:
        if valor.strip().lower() in _SECRET_KEYS_FRACAS or len(valor) < TAMANHO_MINIMO_SECRET_KEY:
            raise ValueError(
                f"SECRET_KEY ausente, de exemplo ou com menos de {TAMANHO_MINIMO_SECRET_KEY} "
                "caracteres. Com ela, qualquer um forja sessão de administrador. Gere uma com "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"` e coloque no .env.'
            )
        return valor


settings = Settings()
