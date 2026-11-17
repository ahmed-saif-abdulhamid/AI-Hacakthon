"""Embeds the ProveIt console (voice HUD) (templates/hud.html.j2, served by the API on
port 8000) inside Streamlit. The HUD talks to the API directly, so voice, telemetry and
the Ask bar work the same as on http://localhost:8000/hud."""
from __future__ import annotations

import os
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components


def api_public_url() -> str:
    return os.environ.get("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def render(mode: str = "hud", height: int = 980) -> None:
    base = api_public_url()
    components.iframe(f"{base}/hud?mode={mode}&embed=1&api={quote(base)}", height=height, scrolling=True)
    st.caption(f"Voice works best full screen: [open the HUD]({base}/hud?mode={mode}) "
               "(browsers may block the microphone inside embedded frames).")
