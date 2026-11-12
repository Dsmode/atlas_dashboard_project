"""Seção "Protegidos": remetentes e domínios que nunca vão para Lixo nem Revisar e não são movidos em lote."""
import pandas as pd
import streamlit as st

from database.triagem import classificacao as cl
from database.triagem import repo

from . import dados


def _adicionar():
    valor = st.session_state.get("tri_novo_protegido", "")
    normalizado = cl.normalizar_protegido(valor)
    if normalizado is None:
        st.session_state.tri_protegido_erro = "Digite um domínio (gupy.io) ou um e-mail (vagas@gupy.io)."
        return
    st.session_state.pop("tri_protegido_erro", None)
    repo.adicionar_protegidos([normalizado])
    dados.renovar_tabelas()
    st.session_state.tri_novo_protegido = ""


def secao():
    repo.garantir_protegidos_padrao(cl.PROTEGIDOS_PADRAO)
    protegidos = repo.listar_protegidos()
    with st.container(key="tri_card_protegidos"):
        st.markdown(
            '<div class="tri-card-titulo">Remetentes protegidos</div>'
            '<div class="tri-texto">Um domínio protegido vale também para os subdomínios (mail.nubank.com.br). '
            'Protegido fica fora de Lixo e de Revisar e só sai da caixa por seleção manual, com confirmação extra. '
            'Se um e-mail de protegido falhar na verificação DMARC, ele vai para Spam e suspeitos: pode ser forjado.'
            '</div>', unsafe_allow_html=True)
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small", key="tri_barra_protegidos"):
            st.text_input("Novo protegido", key="tri_novo_protegido", placeholder="gupy.io ou vagas@gupy.io",
                          on_change=_adicionar)
            st.button("Adicionar", key="tri_adicionar_protegido", type="primary", icon=":material/add:",
                      on_click=_adicionar)
        if st.session_state.get("tri_protegido_erro"):
            st.error(st.session_state.tri_protegido_erro)
        tabela = pd.DataFrame({
            "Remetente ou domínio": [p["valor"] for p in protegidos],
            "Tipo": ["domínio" if p["tipo"] == "dominio" else "e-mail" for p in protegidos],
            "Origem": ["lista inicial" if p["origem"] == "padrao" else "você" for p in protegidos],
        })
        evento = st.dataframe(tabela, hide_index=True, width="stretch", height=min(520, 40 + 35 * len(tabela)),
                              on_select="rerun", selection_mode="multi-row", key=dados.chave_tabela("tri_tabela_protegidos"))
        escolhidos = list(evento.selection.rows)
        if st.button("Remover da lista", key="tri_remover_protegido", icon=":material/delete:",
                     disabled=not escolhidos):
            repo.remover_protegidos([protegidos[i]["valor"] for i in escolhidos])
            dados.renovar_tabelas()
            st.rerun()
