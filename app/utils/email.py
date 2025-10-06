import os
import smtplib
import ssl
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
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

    if not user or not password:
        raise RuntimeError("SMTP credentials missing: set SMTP_USER and SMTP_PASSWORD env vars")

    # Gmail app passwords are often shown with spaces; strip them
    password = password.replace(" ", "")

    context = ssl.create_default_context()

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(user, password)
            server.send_message(message)
        return

    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        if use_tls:
            server.starttls(context=context)
            # Some SMTP servers require EHLO again after STARTTLS
            server.ehlo()
        server.login(user, password)
        server.send_message(message)


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
