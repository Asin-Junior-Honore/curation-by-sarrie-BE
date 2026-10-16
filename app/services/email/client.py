import traceback
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
    Supports both port 587 (STARTTLS) and port 465 (implicit TLS).
    """
    if not settings.smtp_user or not settings.smtp_password:
        print("⚠️  SMTP not configured — skipping email")
        return False

    print(f"📤 SMTP send starting → {to_email}")
    print(f"   host={settings.smtp_host}:{settings.smtp_port}")
    print(f"   from={settings.smtp_from_email or settings.smtp_user}")
    print(f"   subject={subject}")

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

        # ─── Port-aware TLS mode ─────────────────────────
        if settings.smtp_port == 465:
            print("   mode=implicit TLS (port 465)")
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                use_tls=True,
                timeout=30,
            )
        else:
            print("   mode=STARTTLS (port 587)")
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
                timeout=30,
            )

        print(f"📧 ✅ Email sent → {to_email} — {subject}")
        return True

    except Exception as e:
        print(f"❌ Email failed → {to_email}")
        print(f"   error type: {type(e).__name__}")
        print(f"   error: {e}")
        traceback.print_exc()
        return False