"""Seção "Explorar termos": palavras e expressões mais características dos e-mails, grupos sugeridos e a lista de
palavras ignoradas."""
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import repo, tfidf
from database.triagem.estado import fmt_int

from . import dados, editor
from .cards import CARDS

FILTROS = {"todos": "Todos os e-mails", **{card: info["titulo"] for card, info in CARDS.items()}}


def _ignorar(termos):
    repo.adicionar_ruido(tfidf.normalizar_ruido(termos))


def _palavras_ignoradas():
    atuais = repo.listar_ruido()
    with st.popover("Palavras ignoradas", icon=":material/block:"):
        st.markdown(
            "Uma palavra ou expressão por linha. Elas somem dos termos e dos grupos, em qualquer tela. "
            f"Além delas, o ATLAS já ignora uma lista fixa de {fmt_int(len(tfidf.ler_stopwords()))} palavras "
            "comuns do português e do inglês (artigos, preposições, \"click\", \"www\").")
        texto = st.text_area("Palavras ignoradas", value="\n".join(atuais), height=220, label_visibility="collapsed",
                             key="tri_ruido_texto")
        if st.button("Salvar", key="tri_ruido_salvar", type="primary"):
            repo.substituir_ruido(tfidf.normalizar_ruido(texto.splitlines()))
            dados.renovar_tabelas()
            st.session_state.pop("tri_ruido_texto", None)
            st.rerun()


def _palavras_que_salvam():
    atuais = repo.listar_palavras_salvam()
    with st.popover("Palavras que salvam", icon=":material/shield_with_heart:"):
        st.markdown(
            "Um e-mail com uma destas palavras no assunto ou no trecho **nunca cai no Lixo**: vai para Revisar, "
            "de qualquer remetente. Serve para o que importa no meio de promoções (proposta, pedido, boleto). "
            "Uma palavra ou expressão por linha.")
        texto = st.text_area("Palavras que salvam", value="\n".join(atuais), height=220,
                             label_visibility="collapsed", key="tri_salvam_texto")
        if st.button("Salvar", key="tri_salvam_salvar", type="primary"):
            repo.substituir_palavras_salvam(tfidf.normalizar_ruido(texto.splitlines()))
            st.session_state.pop("tri_salvam_texto", None)
            dados.renovar_tabelas()
            st.rerun()


def _grupos(grupos):
    st.markdown('<div class="tri-secao-titulo">Grupos sugeridos</div>', unsafe_allow_html=True)
    if not grupos:
        st.markdown('<div class="tri-texto tri-vazio">Nenhum grupo claro de termos ainda.</div>',
                    unsafe_allow_html=True)
        return
    st.markdown('<div class="tri-nota">Termos que aparecem juntos nos mesmos e-mails. "Criar card" abre o editor '
                'com um critério OU para cada termo, e você ajusta antes de salvar.</div>', unsafe_allow_html=True)
    colunas = st.columns(2)
    for numero, grupo in enumerate(grupos):
        with colunas[numero % 2], st.container(key=f"tri_card_grupo_{numero}"):
            chips = "".join(f'<span class="tri-chip">{escape(t)}</span>' for t in grupo["termos"])
            st.markdown(f'<div class="tri-chips">{chips}</div>'
                        f'<div class="tri-texto"><b>{fmt_int(grupo["emails"])} e-mails</b> têm pelo menos dois '
                        'destes termos.</div>', unsafe_allow_html=True)
            st.button("Criar card", key=f"tri_grupo_card_{numero}", icon=":material/add:",
                      on_click=editor.card_a_partir_de_termos, args=(grupo["termos"],))


def secao():
    caixa = dados.caixa(dados.versao())
    if not caixa["emails"]:
        with st.container(key="tri_card_vazio_termos"):
            st.markdown('<div class="tri-card-titulo">Sem e-mails para analisar</div>'
                        '<div class="tri-texto">Importe a caixa primeiro.</div>', unsafe_allow_html=True)
        return
    with st.container(horizontal=True, vertical_alignment="center", key="tri_barra_termos"):
        filtro = st.segmented_control("Analisar", list(FILTROS), format_func=FILTROS.get, default="todos",
                                      key="tri_filtro_termos", label_visibility="collapsed") or "todos"
        _palavras_ignoradas()
        _palavras_que_salvam()

    with st.spinner("Calculando os termos…"):
        resultado = dados.termos(dados.versao(), filtro)
    itens = resultado["itens"]
    with st.container(key="tri_card_termos"):
        st.markdown(
            '<div class="tri-card-titulo">Explorar termos</div>'
            f'<div class="tri-texto">Palavras e expressões de 1 a 3 palavras que mais caracterizam o assunto e o '
            f'trecho de {fmt_int(resultado["total"])} e-mails. Selecione as que não dizem nada e ignore.</div>',
            unsafe_allow_html=True)
        if not itens:
            st.markdown('<div class="tri-texto tri-vazio">Poucos e-mails para achar termos que se repitam.</div>',
                        unsafe_allow_html=True)
            return
        tabela = pd.DataFrame({
            "Termo": [i["termo"] for i in itens], "E-mails": [i["emails"] for i in itens],
            "Principais remetentes": [", ".join(f"{d} ({n})" for d, n in i["remetentes"]) for i in itens],
        })
        evento = st.dataframe(
            tabela, hide_index=True, width="stretch", height=480, on_select="rerun", selection_mode="multi-row",
            key=dados.chave_tabela(f"tri_tabela_termos_{filtro}"),
            column_config={
                "E-mails": st.column_config.ProgressColumn(min_value=0, max_value=int(tabela["E-mails"].max()),
                                                            format="%d"),
                "Principais remetentes": st.column_config.TextColumn(width="large"),
            })
        escolhidos = list(evento.selection.rows)
        with st.container(horizontal=True, gap="small"):
            if st.button("Ignorar selecionados", key="tri_ignorar", icon=":material/block:", disabled=not escolhidos):
                _ignorar([itens[i]["termo"] for i in escolhidos])
                dados.renovar_tabelas()
                st.rerun()
            st.button("Criar card com os selecionados", key="tri_card_dos_termos", icon=":material/add:",
                      disabled=not escolhidos, on_click=editor.card_a_partir_de_termos,
                      args=([itens[i]["termo"] for i in escolhidos],) if escolhidos else ([""],))
    _grupos(resultado["grupos"])
