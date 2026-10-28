import base64
from datetime import date, datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from database import metas_repo

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def _logo_html():
    if LOGO_PATH.exists():
        dados = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        return f'<img src="data:image/png;base64,{dados}" width="260" alt="ATLAS">'
    return '<div class="logo-placeholder">LOGO</div>'


def _icone(nome):
    return f'<span class="tile-ico"><span class="material-icon">{nome}</span></span>'


def _metas_semanais():
    """Bloco real: metas concluídas / total com prazo na semana atual (domingo a sábado)."""
    hoje = date.today()
    inicio = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
    concluidas, total = metas_repo.contar_metas_no_periodo(inicio, inicio + timedelta(days=6))
    pct = round(concluidas / total * 100) if total else 0
    return (
        f'<div class="home-tile"><div class="tile-head"><span>Metas Semanais</span>{_icone("flag")}</div>'
        f'<div class="tile-value">{concluidas:02d}/{total:02d}</div>'
        f'<div class="tile-note">{pct}% concluído</div>'
        f'<div class="mini-track"><div class="mini-fill" style="width:{pct}%"></div></div></div>'
    )


# "Prazos próximos" é decorativo por enquanto: mostra o formato do que a ferramenta vai exibir.
_PRAZOS = f"""
    <div class="home-tile">
        <div class="tile-head"><span>Prazos próximos</span>{_icone("calendar_month")}</div>
        <div class="tile-line" style="margin-top:1rem">Comprar casa · 15 out.</div>
        <div class="tile-line">Aprender Python · 30 out.</div>
    </div>
"""

_JANELA = 12  # períodos mostrados no gráfico de metas do período
_PERIODOS = {"Semana": ("semana", f"Últimas {_JANELA} semanas"), "Mês": ("mes", f"Últimos {_JANELA} meses")}
# (campo no repositório, rótulo, cor, opacidade): concluídas cheias, pendentes como "vazio" a preencher
_SERIES = [
    ("concluidas", "Concluídas", "#b44cff", 1),
    ("pendentes", "Pendentes", "#b44cff", 0.3),
    ("atrasadas", "Atrasadas", "#ff5c6c", 0.92),
]


def _guardar_periodo():
    """Guarda a escolha Semana/Mês; clicar na opção ativa a desmarcaria, então volta para ela."""
    escolha = st.session_state.home_periodo
    if escolha is None:
        st.session_state.home_periodo = st.session_state.home_periodo_salvo
    else:
        st.session_state.home_periodo_salvo = escolha


def _grafico_periodo(periodos, por):
    """Barras empilhadas por semana ou mês do prazo: concluídas, pendentes e atrasadas."""
    segmentos, totais = [], []
    for p in periodos:
        d = p["inicio"]
        if por == "semana":
            rotulo = f"{d:%d/%m}"
            faixa = f"{d:%d/%m} a {d + timedelta(days=6):%d/%m/%Y}"
        else:
            rotulo = _MESES[d.month - 1].rstrip(".")
            faixa = f"{_MESES[d.month - 1]} de {d.year}"
        soma = sum(p[campo] for campo, *_ in _SERIES)
        totais.append({"rotulo": rotulo, "soma": soma})
        for ordem, (campo, nome, _, opacidade) in enumerate(_SERIES):
            if p[campo]:
                segmentos.append({"rotulo": rotulo, "faixa": faixa, "serie": nome, "ordem": ordem,
                                  "metas": p[campo], "soma": soma, "opacidade": opacidade})
    maior = max(3, max(t["soma"] for t in totais))
    # o domínio fixo mantém a ordem do tempo mesmo com períodos sem nenhuma barra
    eixo_x = alt.X(
        "rotulo:N", sort=None, title=None, scale=alt.Scale(domain=[t["rotulo"] for t in totais]),
        axis=alt.Axis(labelAngle=0, labelOverlap="parity", labelColor="#8d8d9c", labelFontSize=10,
                      ticks=False, domainColor="rgba(255,255,255,.12)", labelPadding=6),
    )
    escala_y = alt.Scale(domain=[0, maior * 1.2])
    nomes = [nome for _, nome, *_ in _SERIES]
    degrade = alt.Gradient(
        gradient="linear", x1=1, y1=0, x2=1, y2=1,
        stops=[alt.GradientStop(color="#d68bff", offset=0), alt.GradientStop(color="#7a2fd1", offset=1)],
    )
    cor = alt.condition(
        f"datum.serie == '{nomes[0]}'", alt.value(degrade),
        alt.Color("serie:N", legend=None, scale=alt.Scale(domain=nomes, range=[c for _, _, c, _ in _SERIES])),
    )
    barras = alt.Chart(pd.DataFrame(segmentos)).mark_bar(
        cornerRadius=2, stroke="#15151b", strokeWidth=1,
    ).encode(
        x=eixo_x,
        y=alt.Y("metas:Q", axis=None, scale=escala_y, stack="zero"),
        color=cor,
        opacity=alt.Opacity("opacidade:Q", legend=None, scale=None),
        order=alt.Order("ordem:Q", sort="ascending"),
        tooltip=[
            alt.Tooltip("faixa:N", title="Período"), alt.Tooltip("serie:N", title="Situação"),
            alt.Tooltip("metas:Q", title="Metas"), alt.Tooltip("soma:Q", title="Total do período"),
        ],
    )
    valores = alt.Chart(pd.DataFrame(totais)).mark_text(dy=-7, color="#d8d8e4", fontSize=11, fontWeight=500).encode(
        x=eixo_x, y=alt.Y("soma:Q", axis=None, scale=escala_y),
        text=alt.condition("datum.soma > 0", "soma:Q", alt.value("")),
    )
    return (
        (barras + valores)
        .properties(height=180)
        .configure(background="transparent", font="Outfit, sans-serif")
        .configure_view(stroke=None)
    )


def _legenda(periodos):
    itens = "".join(
        f'<span class="legenda-item"><i style="background:{cor};opacity:{opac}"></i>{nome} '
        f'<b>{sum(p[campo] for p in periodos)}</b></span>'
        for campo, nome, cor, opac in _SERIES
    )
    return f'<div class="chart-legend">{itens}</div>'


@st.fragment
def _tile_periodo():
    """Cartão real: metas com prazo por semana ou mês, empilhadas (só este trecho recarrega ao trocar)."""
    st.session_state.setdefault("home_periodo_salvo", "Semana")
    with st.container(key="tile_concluidas"):
        st.markdown(
            f'<div class="tile-head"><span>Metas do período</span>{_icone("trending_up")}</div>',
            unsafe_allow_html=True,
        )
        nota = st.empty()
        escolha = st.segmented_control(
            "Período", list(_PERIODOS), default=st.session_state.home_periodo_salvo, key="home_periodo",
            on_change=_guardar_periodo, label_visibility="collapsed", width="stretch",
        ) or st.session_state.home_periodo_salvo
        por, janela = _PERIODOS[escolha]
        periodos = metas_repo.contar_metas_por_periodo(por, _JANELA)
        total = sum(p[campo] for p in periodos for campo, *_ in _SERIES)
        concluidas = sum(p["concluidas"] for p in periodos)
        nota.markdown(
            f'<div class="tile-note">{janela} · {concluidas} de {total} '
            f'{"concluída" if total == 1 else "concluídas"}</div>' + _legenda(periodos),
            unsafe_allow_html=True,
        )
        if total == 0:
            st.markdown('<div class="tile-note">Nenhuma meta com prazo neste período.</div>', unsafe_allow_html=True)
        else:
            st.altair_chart(_grafico_periodo(periodos, por), width="stretch", theme=None)


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
    st.markdown('<div class="home-section-title">Resumo do painel</div>', unsafe_allow_html=True)
    with st.container(key="resumo_grid"):
        st.markdown(_metas_semanais(), unsafe_allow_html=True)
        st.markdown(_PRAZOS, unsafe_allow_html=True)
        _tile_periodo()
    st.markdown(_FUTURO, unsafe_allow_html=True)
