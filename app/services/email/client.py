import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from ...config import settings


async def send_raw_email(
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    """
    Send an HTML email via SMTP.
    Returns True on success, False on failure (never raises).
    """
    if not settings.smtp_user or not settings.smtp_password:
        print("⚠️  SMTP not configured — skipping email")
        return False

    try:
        message = MIMEMultipart("alternative")
        message["From"] = formataddr(
            (
                settings.smtp_from_name,
                settings.smtp_from_email or settings.smtp_user,
            )
        )
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )

        print(f"📧 Email sent → {to_email} — {subject}")
        return True

    except Exception as e:
        print(f"❌ Email failed → {to_email}: {e}")
        return False