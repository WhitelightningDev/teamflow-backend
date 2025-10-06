import os
import smtplib
import ssl
import logging
import socket
from smtplib import SMTPServerDisconnected, SMTPAuthenticationError
import certifi
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _get_env() -> Environment:
    templates_dir = Path(__file__).resolve().parent.parent.parent / "templates" / "email"
    loader = FileSystemLoader(str(templates_dir))
    return Environment(loader=loader, autoescape=select_autoescape(["html", "xml"]))


def render_template(template_name: str, context: Dict[str, Any]) -> str:
    env = _get_env()
    template = env.get_template(template_name)
    return template.render(**context)


def _build_message(subject: str, to: str, html_body: str, text_body: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    from_email = os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", "no-reply@example.com"))
    from_name = os.getenv("FROM_NAME", "TeamFlow")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to
    if text_body:
        msg.set_content(text_body)
    # Add HTML alternative
    msg.add_alternative(html_body, subtype="html")
    return msg


def send_email_smtp(message: EmailMessage) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    timeout = float(os.getenv("SMTP_TIMEOUT", "10"))
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

    if not user or not password:
        raise RuntimeError("SMTP credentials missing: set SMTP_USER and SMTP_PASSWORD env vars")

    # Gmail app passwords are often shown with spaces; strip them
    password = password.replace(" ", "")

    # Auto-correct common port/protocol mismatches
    if port == 465 and not use_ssl:
        logging.getLogger("uvicorn.error").warning("SMTP configured with port 465; enabling SSL and disabling STARTTLS for compatibility")
        use_ssl = True
        use_tls = False
    if port == 587 and use_ssl:
        logging.getLogger("uvicorn.error").warning("SMTP configured with port 587 and SSL; switching to STARTTLS for compatibility")
        use_ssl = False
        use_tls = True

    # Use certifi CA bundle to avoid missing system CAs in slim containers
    context = ssl.create_default_context(cafile=certifi.where())

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
                server.login(user, password)
                server.send_message(message)
            return

        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            if use_tls:
                server.starttls(context=context)
                # Some SMTP servers require EHLO again after STARTTLS
                server.ehlo()
            server.login(user, password)
            server.send_message(message)
    except SMTPAuthenticationError as exc:
        raise RuntimeError(f"SMTP auth failed ({exc.smtp_code}): {exc.smtp_error.decode() if isinstance(exc.smtp_error, bytes) else exc.smtp_error}") from exc
    except (SMTPServerDisconnected, ssl.SSLError, socket.timeout) as exc:
        raise RuntimeError(f"SMTP connection failed: {type(exc).__name__}: {exc}") from exc


def send_invite_email(*, to: str, invite_url: str, company_name: str = "TeamFlow", employee_first_name: str | None = None) -> None:
    html = render_template(
        "invite.html",
        {
            "company_name": company_name,
            "invite_url": invite_url,
            "employee_first_name": employee_first_name or "there",
        },
    )
    text = f"Hello {employee_first_name or 'there'},\n\nYou have been invited to {company_name}.\nAccept your invite: {invite_url}\n\nIf you didn’t expect this, you can ignore this email."
    msg = _build_message(
        subject=f"You're invited to {company_name}",
        to=to,
        html_body=html,
        text_body=text,
    )
    send_email_smtp(msg)
