from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://nfe_user:nfe_pass@db:3306/nfe_sistema"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    secret_key: str = "change-me"

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

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    email_from: str = "no-reply@leitorxml.local"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
