from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ...config import settings

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template_name: str, context: dict) -> str:
    """Render a Jinja2 template with brand defaults."""
    context.setdefault("brand_name", settings.business_name)
    context.setdefault("brand_url", settings.frontend_url)
    context.setdefault("business_address", settings.business_address)
    context.setdefault("business_phone", settings.business_phone)
    context.setdefault("business_email", settings.business_email)
    context.setdefault("business_whatsapp", settings.business_whatsapp)

    template = env.get_template(template_name)
    return template.render(**context)