from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClienteCasoCreate(BaseModel):
    """Campos que o usuário informa ao cadastrar um cliente/caso."""

    nome_cliente: str
    identificacao_caso: str | None = None


class ClienteCasoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome_cliente: str
    identificacao_caso: str | None
    criado_em: datetime
