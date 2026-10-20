from pathlib import Path

import streamlit as st

from database.connection import init_db
from modules import home, metas

st.set_page_config(page_title="ATLAS", page_icon="🪐", layout="wide")

CSS_PATH = Path(__file__).parent / "assets" / "style.css"
st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# Para adicionar um módulo novo: criar modules/<nome>.py com render() e registrar aqui.
MODULOS = {
    "Início": (":material/home:", home.render),
    "Metas Pessoais": (":material/flag:", metas.render),
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

with st.sidebar:
    st.markdown('<div class="atlas-brand"><span class="dot"></span>ATLAS</div>', unsafe_allow_html=True)
    st.markdown('<div class="atlas-nav-label">MÓDULOS</div>', unsafe_allow_html=True)
    for nome, (icone, _) in MODULOS.items():
        ativo = st.session_state.pagina == nome
        if st.button(nome, icon=icone, key=f"nav_{nome}", use_container_width=True,
                     type="primary" if ativo else "secondary"):
            st.session_state.pagina = nome
            st.rerun()

MODULOS[st.session_state.pagina][1]()
