"""
email_service.py — VoidLog v3
Funções utilitárias para envio de e-mail via SMTP.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def enviar_email(cfg: dict, destino: str, assunto: str, corpo: str):
    """
    cfg deve ter: email_smtp_host, email_smtp_port, email_smtp_user, email_smtp_pass
    """
    host  = cfg.get("email_smtp_host", "")
    port  = int(cfg.get("email_smtp_port", 587))
    user  = cfg.get("email_smtp_user", "")
    senha = cfg.get("email_smtp_pass", "")

    if not host or not user:
        raise ValueError("Configuração de SMTP incompleta")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = user
    msg["To"]      = destino

    html_body = f"""
    <html><body style="font-family:sans-serif;background:#f5f5f5;padding:20px">
      <div style="max-width:600px;margin:auto;background:#fff;border-radius:8px;padding:24px;
                  box-shadow:0 2px 8px rgba(0,0,0,.1)">
        <h2 style="color:#1a1a2e;border-bottom:2px solid #e94560;padding-bottom:8px">VoidLog</h2>
        <pre style="background:#f8f8f8;padding:16px;border-radius:4px;font-size:13px">{corpo}</pre>
        <p style="color:#999;font-size:11px;margin-top:16px">Mensagem automática — VoidLog v3</p>
      </div>
    </body></html>
    """

    msg.attach(MIMEText(corpo, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, senha)
        smtp.sendmail(user, destino, msg.as_string())
