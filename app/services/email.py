import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from typing import Optional

from ..config import settings

# Jinja2 setup — templates live in backend/app/templates/
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


async def send_email(
    to_email: str,
    subject: str,
    template_name: str,
    context: Optional[dict] = None,
) -> bool:
    """
    Send an HTML email using a Jinja2 template.

    Args:
        to_email: Recipient email
        subject: Email subject
        template_name: e.g. "admin_invite.html"
        context: Dict of variables passed to the template
    """
    if context is None:
        context = {}

    context.setdefault("brand_name", "Curation by Sarrie")
    context.setdefault("brand_url", "https://curationbysarrie.netlify.app")

    try:
        # Render HTML
        template = env.get_template(template_name)
        html_body = template.render(**context)

        # Build the message
        message = MIMEMultipart("alternative")
        message["From"] = formataddr(
            (settings.smtp_from_name, settings.smtp_from_email or settings.smtp_user)
        )
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        # Send via SMTP
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )

        print(f"📧 Email sent to {to_email} — {subject}")
        return True

    except Exception as e:
        print(f"❌ Email failed to {to_email}: {e}")
        return False