import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("chave", ["", "change-me", "CHANGE-ME", "curta-demais", "troque_por_uma_chave_secreta_longa"])
def test_secret_key_fraca_impede_a_subida(chave):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(secret_key=chave, _env_file=None)


def test_secret_key_forte_e_aceita():
    chave = "x" * 48
    assert Settings(secret_key=chave, _env_file=None).secret_key == chave
