import smtplib
from email.message import EmailMessage

from app.core.config import settings


def enviar_email(destinatario: str, assunto: str, corpo: str) -> None:
    """Envio simples via SMTP. Em dev, `settings.smtp_host` aponta para o
    serviço mailhog do docker-compose (não envia e-mail de verdade)."""
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.email_from
    msg["To"] = destinatario
    msg.set_content(corpo)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
