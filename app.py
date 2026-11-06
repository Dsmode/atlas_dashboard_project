import base64
from pathlib import Path

import streamlit as st

from database.connection import init_db
from modules import financas, home, metas
from modules.metas.cartao import recolher_cartoes
from modules.ui import corpo_ativo

ASSETS = Path(__file__).parent / "assets"
_favicon = ASSETS / "favicon.png"

st.set_page_config(page_title="ATLAS", page_icon=str(_favicon) if _favicon.exists() else "🪐", layout="wide")

# A rede de fundo e a fonte entram no CSS como data URI (marcadores __REDE__ e __FONTE__): o app não depende de
# arquivos servidos nem de internet.
_rede = base64.b64encode((ASSETS / "rede.svg").read_bytes()).decode()
_fonte = base64.b64encode((ASSETS / "fonts" / "outfit-latin.woff2").read_bytes()).decode()
_css = (
    (ASSETS / "style.css").read_text(encoding="utf-8")
    .replace("__REDE__", f"data:image/svg+xml;base64,{_rede}")
    .replace("__FONTE__", f"data:font/woff2;base64,{_fonte}")
)
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)

# Para criar um módulo: modules/<nome>.py com render(), registrado aqui.
MODULOS = {
    "Início": (":material/home:", home.render),
    "Metas Pessoais": (":material/flag:", metas.render),
    "Controle Financeiro": (":material/account_balance_wallet:", financas.render),
}


@st.cache_resource
def _preparar_banco():
    init_db()


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
    if st.button(nome, icon=icone, key=f"nav_{nome}", width="stretch",
                 type="primary" if ativo else "secondary"):
        st.session_state.pagina = nome
        recolher_cartoes()
        st.rerun()


# Conta de exemplo, só para a sidebar. Sai quando existir login.
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

with corpo_ativo(MODULOS, st.session_state.pagina, "modulo_"):
    MODULOS[st.session_state.pagina][1]()
