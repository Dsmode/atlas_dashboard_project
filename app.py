import base64
from pathlib import Path

import streamlit as st

from database.connection import init_db
from modules import financas, home, metas

ASSETS = Path(__file__).parent / "assets"
_favicon = ASSETS / "favicon.png"

# ícone da aba do navegador: o A recortado da logo (emoji enquanto o arquivo não existir)
st.set_page_config(page_title="ATLAS", page_icon=str(_favicon) if _favicon.exists() else "🪐", layout="wide")

# a rede geométrica do fundo é um SVG embutido no CSS (o marcador __REDE__ vira um data URI)
_rede = base64.b64encode((ASSETS / "rede.svg").read_bytes()).decode()
_css = (ASSETS / "style.css").read_text(encoding="utf-8").replace("__REDE__", f"data:image/svg+xml;base64,{_rede}")
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)

# Para adicionar um módulo novo: criar modules/<nome>.py com render() e registrar aqui.
MODULOS = {
    "Início": (":material/home:", home.render),
    "Metas Pessoais": (":material/flag:", metas.render),
    "Controle Financeiro": (":material/account_balance_wallet:", financas.render),
}


@st.cache_resource
def _preparar_banco():
    init_db()
    return True


try:
    _preparar_banco()
except Exception as erro:
    st.error(
        "Não foi possível conectar ao MySQL. Confira se o serviço MySQL80 está ativo "
        f"e se as credenciais do arquivo .env estão corretas.\n\nDetalhe: {erro}"
    )
    st.stop()

if "pagina" not in st.session_state:
    st.session_state.pagina = "Início"

def _item_menu(nome):
    icone = MODULOS[nome][0]
    ativo = st.session_state.pagina == nome
    if st.button(nome, icon=icone, key=f"nav_{nome}", use_container_width=True,
                 type="primary" if ativo else "secondary"):
        st.session_state.pagina = nome
        metas.recolher_cartoes()
        st.rerun()


# dados de exemplo da conta (visual por enquanto; virão do login)
CONTA = {"iniciais": "VC", "nome": "Vinicius", "email": "vinicius@exemplo.com"}

with st.sidebar:
    st.markdown('<div class="atlas-brand"><span class="dot"></span>ATLAS</div>', unsafe_allow_html=True)
    _item_menu("Início")
    st.markdown('<div class="atlas-nav-label">FERRAMENTAS</div>', unsafe_allow_html=True)
    for nome in MODULOS:
        if nome != "Início":
            _item_menu(nome)
    with st.container(key="atlas_conta"):
        st.markdown(
            f'<div class="conta-avatar">{CONTA["iniciais"]}</div>'
            f'<div class="conta-info"><div class="conta-nome">{CONTA["nome"]}</div>'
            f'<div class="conta-email">{CONTA["email"]}</div></div>'
            '<div class="conta-setas"><span>expand_less</span><span>expand_more</span></div>',
            unsafe_allow_html=True,
        )

MODULOS[st.session_state.pagina][1]()
