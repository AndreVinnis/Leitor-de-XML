from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.core.email import enviar_email


@patch("app.core.email.smtplib.SMTP")
def test_enviar_email_monta_mensagem_e_conecta_no_host_configurado(mock_smtp_cls, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.teste")
    monkeypatch.setattr(settings, "smtp_port", 2525)
    monkeypatch.setattr(settings, "smtp_use_tls", False)
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "email_from", "de@teste.com")

    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    enviar_email("para@teste.com", "Assunto", "Corpo do e-mail")

    mock_smtp_cls.assert_called_once_with("smtp.teste", 2525)
    mock_smtp.send_message.assert_called_once()

    mensagem = mock_smtp.send_message.call_args[0][0]
    assert mensagem["To"] == "para@teste.com"
    assert mensagem["From"] == "de@teste.com"
    assert mensagem["Subject"] == "Assunto"
    assert mensagem.get_content().strip() == "Corpo do e-mail"

    mock_smtp.starttls.assert_not_called()
    mock_smtp.login.assert_not_called()


@patch("app.core.email.smtplib.SMTP")
def test_enviar_email_com_tls_e_autenticacao(mock_smtp_cls, monkeypatch):
    monkeypatch.setattr(settings, "smtp_use_tls", True)
    monkeypatch.setattr(settings, "smtp_user", "usuario-smtp")
    monkeypatch.setattr(settings, "smtp_password", "senha-smtp")

    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    enviar_email("para@teste.com", "Assunto", "Corpo")

    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("usuario-smtp", "senha-smtp")
