import base64
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def _logo_html():
    if LOGO_PATH.exists():
        dados = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        return f'<img src="data:image/png;base64,{dados}" width="200" style="margin:2rem 0 1rem 0">'
    return '<div class="logo-placeholder">LOGO</div>'


def render():
    st.markdown(
        f"""
        <div class="home-wrap">
            {_logo_html()}
            <h1>ATLAS</h1>
            <p class="atlas-sub">Bem-vindo ao seu dashboard pessoal. Escolha um módulo na barra lateral para começar.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
