"""The Jinja environment for the HTML pages a run produces (landing page, store page)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


@lru_cache(maxsize=1)
def environment() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html", "j2"]))


def render_page(template: str, **context) -> str:
    return environment().get_template(template).render(**context)
