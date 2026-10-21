import base64
from datetime import datetime
from pathlib import Path

import streamlit as st

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def _logo_html():
    if LOGO_PATH.exists():
        dados = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        return f'<img src="data:image/png;base64,{dados}" width="200" alt="ATLAS">'
    return '<div class="logo-placeholder">LOGO</div>'


def _icone(nome):
    return f'<span class="tile-ico"><span class="material-icon">{nome}</span></span>'


# Os cartões do resumo são decorativos por enquanto: mostram o formato do que cada ferramenta vai exibir.
_RESUMO = f"""
<div class="home-section-title">Resumo do painel</div>
<div class="home-grid">
    <div class="home-tile">
        <div class="tile-head"><span>Metas ativas</span>{_icone("flag")}</div>
        <div class="tile-value">5</div>
        <div class="mini-track"><div class="mini-fill" style="width:22%"></div></div>
    </div>
    <div class="home-tile">
        <div class="tile-head"><span>Prazos próximos</span>{_icone("calendar_month")}</div>
        <div class="tile-line" style="margin-top:1rem">Comprar casa · 15 out.</div>
        <div class="tile-line">Aprender Python · 30 out.</div>
    </div>
    <div class="home-tile">
        <div class="tile-head"><span>Visão semanal</span>{_icone("trending_up")}</div>
        <svg class="tile-spark" viewBox="0 0 200 70" preserveAspectRatio="none" aria-hidden="true">
            <defs><linearGradient id="sp" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#b44cff" stop-opacity=".45"/><stop offset="1" stop-color="#b44cff" stop-opacity="0"/>
            </linearGradient></defs>
            <path d="M0 58 C25 50 35 40 60 44 S100 22 125 30 S165 12 200 8 L200 70 L0 70 Z" fill="url(#sp)"/>
            <path d="M0 58 C25 50 35 40 60 44 S100 22 125 30 S165 12 200 8" fill="none" stroke="#b44cff" stroke-width="2"/>
        </svg>
    </div>
</div>
"""


def _bloco(titulo, corpo, classe=""):
    return (
        f'<div class="home-tile {classe}"><div class="tile-head"><span>{titulo}</span>'
        f'<span class="soon">Em breve</span></div>{corpo}</div>'
    )


_LINHAS = '<div class="skel s1"></div><div class="skel s2"></div><div class="skel s3"></div>'
_BARRAS = '<div class="skel-bars">' + "".join(
    f'<i style="height:{h}%"></i>' for h in (35, 60, 45, 80, 55, 95, 70, 50)
) + "</div>"

# Blocos reservados para as informações das próximas ferramentas.
_FUTURO = (
    '<div class="home-section-title">Novidades das ferramentas</div><div class="home-grid">'
    + _bloco("Atividade recente", _LINHAS * 2, "wide tall")
    + _bloco("Próxima ferramenta", _LINHAS)
    + _bloco("Evolução do mês", _BARRAS, "tall")
    + _bloco("Lembretes", _LINHAS, "tall")
    + _bloco("Destaques", _LINHAS, "tall")
    + _bloco("Linha do tempo", _LINHAS * 2, "wide")
    + _bloco("Resumo financeiro", _BARRAS)
    + "</div>"
)


_MESES = ["jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez."]


@st.fragment(run_every="30s")
def _relogio():
    agora = datetime.now()
    st.markdown(
        f'<div class="home-clock"><span class="material-icon">calendar_today</span>'
        f'{agora.day} de {_MESES[agora.month - 1]} de {agora.year}, {agora:%H:%M}</div>',
        unsafe_allow_html=True,
    )


def render():
    _relogio()
    st.markdown(
        f"""
        <div class="home-hero">
            {_logo_html()}
            <h1>ATLAS</h1>
            <p class="atlas-sub">Bem-vindo ao seu portal pessoal. Comece a transformar seus planos em ações.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(_RESUMO, unsafe_allow_html=True)
    st.markdown(_FUTURO, unsafe_allow_html=True)
