from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema
from jinja2 import Environment, FileSystemLoader

from app.config import settings

_template_dir = Path(__file__).resolve().parent.parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_template_dir)))

_mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.smtp_user or "",
    MAIL_PASSWORD=settings.smtp_pass or "",
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.smtp_port,
    MAIL_SERVER=settings.smtp_host,
    MAIL_STARTTLS=settings.smtp_starttls,
    MAIL_SSL_TLS=settings.smtp_ssl_tls,
    USE_CREDENTIALS=bool(settings.smtp_user),
)

fast_mail = FastMail(_mail_conf)


async def send_expiry_alert_email(
    recipients: list[str],
    document: dict,
    days_remaining: int,
    severity: str = "early",
) -> None:
    template = _jinja_env.get_template("expiry_alert.html")
    html = template.render(
        crew_member_name=document.get("seafarer_name", "Crew Member"),
        document_type=document.get("document_type", "Document"),
        document_number=document.get("document_number", ""),
        expiry_date=document.get("expiry_date", ""),
        days_remaining=days_remaining,
        threshold_value=document.get("alert_threshold_days", ""),
        severity=severity,
        dashboard_link=document.get("dashboard_link", f"{settings.frontend_url}/documents"),
    )

    message = MessageSchema(
        subject=f"Document Expiry Alert: {document.get('document_type', 'Document')} expires in {days_remaining} days",
        recipients=recipients,
        body=html,
        subtype="html",
    )
    await fast_mail.send_message(message)
