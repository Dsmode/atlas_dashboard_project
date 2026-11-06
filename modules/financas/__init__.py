from datetime import date
from pathlib import Path

import streamlit as st

from database.financas import calculos as calc
from modules.financas import configuracoes, dashboard, extrato, importar
from modules.ui import corpo_ativo

CSS_DIR = Path(__file__).resolve().parents[2] / "assets" / "financas"

# chave: (rótulo, ícone, função que desenha a aba recebendo o mês ativo)
ABAS = {
    "dashboard": ("Dashboard", ":material/space_dashboard:", dashboard.render),
    "extrato": ("Extrato", ":material/receipt_long:", extrato.render),
    "importar": ("Importar", ":material/upload_file:", importar.render),
}


@st.cache_resource(max_entries=1)
def _ler_css(versao):
    """Relê os .css só quando a data de modificação muda: editar um arquivo vale no próximo rerun."""
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(CSS_DIR.glob("*.css")))


def _css():
    """Injeta o CSS do módulo (base mais um arquivo por aba) só enquanto ele está aberto. Vai por st.markdown
    porque um st.html só com <style> não chegou ao DOM."""
    versao = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(CSS_DIR.glob("*.css")))
    st.markdown(f"<style>{_ler_css(versao)}</style>", unsafe_allow_html=True)


# Mês e aba ficam em session_state para sobreviver à troca de módulo.
def mes_ativo():
    return st.session_state.setdefault("fin_mes", calc.inicio_mes(date.today()))


def _mudar_mes(n):
    st.session_state.fin_mes = calc.somar_meses(mes_ativo(), n)


def _mes_atual():
    st.session_state.fin_mes = calc.inicio_mes(date.today())


def _seletor_mes():
    mes = mes_ativo()
    with st.container(horizontal=True, gap="xsmall", vertical_alignment="center", width="content",
                      key="fin_mes_nav"):
        st.button("", icon=":material/chevron_left:", key="fin_mes_ant", help="Mês anterior",
                  on_click=_mudar_mes, args=(-1,))
        st.button(calc.nome_mes(mes), key="fin_mes_rotulo", on_click=_mes_atual,
                  help="Voltar ao mês atual" if mes != calc.inicio_mes(date.today()) else None)
        st.button("", icon=":material/chevron_right:", key="fin_mes_prox", help="Próximo mês",
                  on_click=_mudar_mes, args=(1,))


def _escolher_aba(chave):
    st.session_state.fin_aba = chave


def _abas():
    ativa = st.session_state.setdefault("fin_aba", "dashboard")
    with st.container(horizontal=True, gap="small", key="fin_abas"):
        for chave, (rotulo, icone, _) in ABAS.items():
            st.button(rotulo, icon=icone, key=f"fin_aba_{chave}", width="stretch",
                      type="primary" if chave == ativa else "secondary",
                      on_click=_escolher_aba, args=(chave,))
    return ativa


def render():
    _css()
    with st.container(key="fin_raiz"):
        topo, acoes = st.columns([3, 2], vertical_alignment="center")
        topo.markdown(
            '<div class="atlas-title">Controle Financeiro</div>'
            '<div class="atlas-sub">Entradas, gastos e para onde vai o seu dinheiro</div>',
            unsafe_allow_html=True,
        )
        with acoes, st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                                 gap="small", key="fin_topo_acoes"):
            _seletor_mes()
            if st.button("", icon=":material/settings:", key="fin_config", help="Configurações de finanças"):
                configuracoes.abrir()
        aba = _abas()
        with corpo_ativo(ABAS, aba, "fin_corpo_"):
            ABAS[aba][2](mes_ativo())
