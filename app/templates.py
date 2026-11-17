"""The shared Jinja environment for the console and the designed status pages."""

from __future__ import annotations

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.settings import TEMPLATES_DIR

HUD_TEMPLATE = "hud.html.j2"
STATUS_TEMPLATE = "status.html.j2"
CONSOLE_PATH = "/hud"

templates = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "j2"]))


def render(name: str, **context: object) -> str:
    return templates.get_template(name).render(**context)


def status_page(
    status: int,
    title: str,
    body: str,
    *,
    back: str = CONSOLE_PATH,
    back_label: str = "Back to ProveIt",
    tone: str = "plain",
    actions: list[dict[str, str]] | None = None,
    refund_order: str | None = None,
) -> HTMLResponse:
    """A designed full-page message (errors, confirmations) with a link back to where the visitor came from."""
    html = render(
        STATUS_TEMPLATE,
        status=status,
        title=title,
        body=body,
        back=back,
        back_label=back_label,
        tone=tone,
        actions=actions,
        refund_order=refund_order,
    )
    return HTMLResponse(html, status_code=status)
