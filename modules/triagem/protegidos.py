"""Seção "Bloqueios e protegidos": golpes marcados por você, remetentes protegidos e os e-mails dos protegidos."""
import pandas as pd
import streamlit as st

from database.triagem import classificacao as cl
from database.triagem import repo
from database.triagem.estado import fmt_int

from . import acoes, dados


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


def _adicionar_bloqueio():
    normalizado = cl.normalizar_protegido(st.session_state.get("tri_novo_bloqueio", ""))
    if normalizado is None:
        st.session_state.tri_bloqueio_erro = "Digite um domínio (golpe.xyz) ou um e-mail (x@golpe.xyz)."
        return
    st.session_state.pop("tri_bloqueio_erro", None)
    repo.adicionar_bloqueados([normalizado], "Bloqueado por você")
    dados.renovar_tabelas()
    st.session_state.tri_novo_bloqueio = ""


def _bloqueados():
    bloqueados = repo.listar_bloqueados()
    with st.container(key="tri_card_bloqueados"):
        st.markdown(
            '<div class="tri-card-titulo">Bloqueados (golpes)</div>'
            '<div class="tri-texto">E-mails destes remetentes vão para Spam e suspeitos, antes de qualquer protegido ou '
            'regra de card. O ATLAS nunca abre links deles. Domínio bloqueado vale para os subdomínios.</div>',
            unsafe_allow_html=True)
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small", key="tri_barra_bloqueados"):
            st.text_input("Novo bloqueio", key="tri_novo_bloqueio", placeholder="golpe.xyz ou x@golpe.xyz",
                          on_change=_adicionar_bloqueio)
            st.button("Bloquear", key="tri_adicionar_bloqueio", type="primary", icon=":material/gpp_bad:",
                      on_click=_adicionar_bloqueio)
        if st.session_state.get("tri_bloqueio_erro"):
            st.error(st.session_state.tri_bloqueio_erro)
        if not bloqueados:
            st.markdown('<div class="tri-texto tri-vazio">Nenhum remetente bloqueado.</div>', unsafe_allow_html=True)
            return
        tabela = pd.DataFrame({
            "Remetente ou domínio": [b["valor"] for b in bloqueados],
            "Tipo": ["domínio" if b["tipo"] == "dominio" else "e-mail" for b in bloqueados],
            "Desde": [b["criado_em"].strftime("%d/%m/%Y") for b in bloqueados],
        })
        evento = st.dataframe(tabela, hide_index=True, width="stretch", height=min(360, 50 + 35 * len(tabela)),
                              on_select="rerun", selection_mode="multi-row",
                              key=dados.chave_tabela("tri_tabela_bloqueados"))
        escolhidos = list(evento.selection.rows)
        if st.button("Desbloquear", key="tri_desbloquear", icon=":material/lock_open:", disabled=not escolhidos):
            repo.remover_bloqueados([bloqueados[i]["valor"] for i in escolhidos])
            dados.renovar_tabelas()
            st.rerun()


def _emails_de_protegidos():
    caixa = dados.caixa(dados.versao())
    ids = {i for i, (c, _) in caixa["classificacao"].items() if c == cl.PROTEGIDO}
    linhas = cl.remetentes_de(caixa["emails"], ids, lambda e: "Remetente protegido")
    with st.container(key="tri_card_protegidos_emails"):
        st.markdown(
            '<div class="tri-card-titulo">E-mails de protegidos</div>'
            f'<div class="tri-texto">{fmt_int(len(ids))} e-mails de {fmt_int(len(linhas))} remetentes protegidos. '
            'Nenhuma ação em card toca neles. Aqui você pode movê-los para a lixeira à mão, com confirmação extra.'
            '</div>', unsafe_allow_html=True)
        if not linhas:
            return
        tabela = pd.DataFrame({
            "Nome": [l["nome"] for l in linhas], "Remetente": [l["remetente"] for l in linhas],
            "E-mails": [l["emails"] for l in linhas], "Lidos": [l["lidos"] for l in linhas],
        })
        evento = st.dataframe(
            tabela, hide_index=True, width="stretch", height=min(420, 50 + 35 * len(tabela)), on_select="rerun",
            selection_mode="multi-row", key=dados.chave_tabela("tri_tabela_protegidos_emails"),
            column_config={"E-mails": st.column_config.NumberColumn(format="%d", width=80),
                           "Lidos": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent",
                                                                    width=100)})
        escolhidos = list(evento.selection.rows)
        selecionados = acoes.ids_dos_remetentes(caixa, ids, [linhas[i]["remetente"] for i in escolhidos])
        if st.button(f"Mover para a lixeira ({fmt_int(len(selecionados))})", key="tri_lix_protegidos",
                     icon=":material/delete:", disabled=not selecionados):
            acoes.pedir_lixeira(caixa, selecionados, "Protegidos", extra=True)


def secao():
    _bloqueados()
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
    _emails_de_protegidos()
