from functools import lru_cache
from pathlib import Path

import streamlit as st

JS = Path(__file__).resolve().parent.parent / "assets" / "js"


def plural(n, singular, plural_):
    return f"{n} {singular if n == 1 else plural_}"


def secao(icone, titulo):
    st.markdown(
        f'<div class="dlg-sec"><span class="material-icon">{icone}</span>{titulo}</div>', unsafe_allow_html=True,
    )


def escolha(rotulos, chave, atual, descricao, **opcoes):
    """Segmented control que nunca fica sem seleção. Devolve a chave de `rotulos`."""
    escolhido = st.segmented_control(
        descricao, list(rotulos.values()), default=rotulos[atual], key=chave, label_visibility="collapsed", **opcoes,
    )
    return next((k for k, v in rotulos.items() if v == escolhido), atual)


def agendar_aviso(chave, texto):
    """O toast só aparece na próxima execução: um st.rerun logo depois de chamá-lo apagaria a mensagem."""
    st.session_state[chave] = texto


def mostrar_aviso(chave):
    texto = st.session_state.pop(chave, None)
    if texto:
        st.toast(texto, icon=":material/check_circle:")


def corpo_ativo(nomes, ativo, prefixo):
    """Reserva uma posição na página para cada nome, na mesma ordem sempre, mas só o ativo vira container; os
    outros viram st.empty(). Assim a tela anterior some na hora, em vez de ficar esmaecida até o novo corpo
    terminar de desenhar."""
    corpos = {nome: st.container(key=f"{prefixo}{nome}") if nome == ativo else st.empty() for nome in nomes}
    return corpos[ativo]


@lru_cache
def script(nome):
    return "<script>\n" + (JS / f"{nome}.js").read_text(encoding="utf-8") + "</script>"
