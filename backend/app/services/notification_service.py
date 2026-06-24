import asyncio
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from app.config import settings

_template_dir = Path(__file__).resolve().parent.parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_template_dir)))

resend.api_key = settings.resend_api_key


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

    params = {
        "from": f"Maritime Crew Monitor <{settings.mail_from}>",
        "to": recipients,
        "subject": f"Document Expiry Alert: {document.get('document_type', 'Document')} expires in {days_remaining} days",
        "html": html,
    }

    await asyncio.to_thread(resend.Emails.send, params)
