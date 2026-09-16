from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.validadores import validar_cnpj_obrigatorio

# Usada tanto na criação quanto na edição de caso: CNPJ é obrigatório nos
# dois fluxos, então mesmo em ClienteCasoUpdate (campos opcionais para
# permitir atualização parcial) o valor, quando informado, nunca pode ser
# vazio/nulo -- não existe "limpar o CNPJ" via PATCH.
_normalizar_cnpj_obrigatorio = validar_cnpj_obrigatorio


class ClienteCasoCreate(BaseModel):
    """Campos que o usuário informa ao cadastrar um cliente/caso."""

    nome_cliente: str
    identificacao_caso: str | None = None
    cnpj_cliente: str

    @field_validator("cnpj_cliente")
    @classmethod
    def validar_cnpj_cliente(cls, valor: str) -> str:
        return _normalizar_cnpj_obrigatorio(valor)


class ClienteCasoUpdate(BaseModel):
    """Campos editáveis de um cliente/caso já existente. nome_cliente e
    identificacao_caso são opcionais (permite atualização parcial), mas
    cnpj_cliente -- quando enviado -- nunca pode ser vazio (ver
    _normalizar_cnpj_obrigatorio). O default None aqui só existe para
    permitir omitir o campo num PATCH que não mexe no CNPJ; o validator não
    roda sobre esse default (Pydantic não valida valores default por
    padrão), então omitir o campo não dispara o erro de obrigatoriedade.
    """

    nome_cliente: str | None = None
    identificacao_caso: str | None = None
    cnpj_cliente: str | None = None

    @field_validator("cnpj_cliente")
    @classmethod
    def validar_cnpj_cliente(cls, valor: str | None) -> str:
        return _normalizar_cnpj_obrigatorio(valor)


class ClienteCasoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome_cliente: str
    identificacao_caso: str | None
    cnpj_cliente: str | None
    criado_em: datetime
