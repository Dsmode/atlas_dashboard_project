from decimal import Decimal

import streamlit as st

from database.dinheiro import VALOR_MAX
from database.metas import repo


def _ajustar_quantidade(meta_id, delta):
    repo.somar_valor(meta_id, Decimal(delta), minimo=Decimal(0))


def _digitou_quantidade(meta_id, chave):
    digitado = int(st.session_state[chave])
    if digitado < 0:
        st.toast("A quantidade não pode ser negativa; ajustei para 0.")
    repo.definir_valor_atual(meta_id, Decimal(max(digitado, 0)), minimo=Decimal(0))


def controle_quantidade(meta):
    """[ − ] valor [ + ], com o valor central editável. O banco é a fonte da verdade: a chave leva o valor atual,
    então o campo é recriado com o número certo depois de cada gravação."""
    meta_id = meta["id"]
    atual = int(meta["valor_atual"] or 0)
    chave = f"qtd_{meta_id}_{atual}"
    with st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key=f"meta_qtd_{meta_id}"):
        st.button("", icon=":material/remove:", key=f"qtd_menos_{meta_id}", help="Diminuir 1",
                  disabled=atual <= 0, on_click=_ajustar_quantidade, args=(meta_id, -1))
        st.number_input("Quantidade atual", value=atual, max_value=int(VALOR_MAX), step=1, format="%d", key=chave,
                        label_visibility="collapsed", on_change=_digitou_quantidade, args=(meta_id, chave))
        st.button("", icon=":material/add:", key=f"qtd_mais_{meta_id}", help="Aumentar 1",
                  on_click=_ajustar_quantidade, args=(meta_id, 1))


def _aplicar_valor(meta_id, sinal, chave, reinicio):
    """Lê o campo na hora do clique, quando o estado do widget já está em dia."""
    valor = Decimal(str(round(st.session_state[chave], 2)))
    if valor <= 0:
        st.toast("Informe um valor maior que zero.")
        return
    delta = valor * sinal
    novo = repo.somar_valor(meta_id, delta)
    st.session_state[reinicio] = st.session_state.get(reinicio, 0) + 1  # o campo volta a zero
    if novo < 0 <= novo - delta:
        st.toast("O saldo ficou negativo.")


def controle_valor(meta):
    """Campo em R$ com Adicionar e Remover (Acrescentar e Abater nas metas de redução)."""
    meta_id = meta["id"]
    reinicio = f"val_reinicio_{meta_id}"
    chave = f"val_{meta_id}_{st.session_state.get(reinicio, 0)}"
    reduzir = meta["objetivo"] == "reduzir"
    botoes = [("Abater", "menos", -1, "remove"), ("Acrescentar", "mais", 1, "add")] if reduzir else [
        ("Adicionar", "mais", 1, "add"), ("Remover", "menos", -1, "remove")]
    with st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key=f"meta_val_{meta_id}"):
        st.markdown('<span class="val-prefixo">R$</span>', unsafe_allow_html=True)
        st.number_input("Valor (R$)", min_value=0.0, max_value=float(VALOR_MAX), step=0.01, format="%.2f", key=chave,
                        label_visibility="collapsed", width="stretch")
        for rotulo, nome, sinal, icone in botoes:
            st.button(rotulo, icon=f":material/{icone}:", key=f"val_{nome}_{meta_id}",
                      on_click=_aplicar_valor, args=(meta_id, sinal, chave, reinicio))
