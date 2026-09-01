from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://nfe_user:nfe_pass@db:3306/nfe_sistema"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    secret_key: str = "change-me"

    api_base_url: str = "http://localhost:8000"
    token_aprovacao_expira_minutos: int = 30

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    email_from: str = "no-reply@leitorxml.local"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
