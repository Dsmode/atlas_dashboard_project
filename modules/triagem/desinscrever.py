"""Seção "Desinscrever": remetentes de lista (com List-Unsubscribe). Nada acontece sem a sua aprovação."""
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import classificacao as cl
from database.triagem import desinscricao, repo
from database.triagem.estado import fmt_int

from . import dados

MAX_LINKS_ABERTOS = 5


def _linhas(caixa, achados, feitas):
    por_remetente = {}
    for e in caixa["emails"]:
        remetente = (e["remetente_email"] or "").lower()
        if remetente not in achados or e["enviado"] or e["lixeira"]:
            continue
        g = por_remetente.setdefault(remetente, {"nome": e["remetente_nome"] or "", "emails": 0, "lidos": 0, "suspeito": 0})
        g["emails"] += 1
        g["lidos"] += 1 if e["lido"] else 0
        g["suspeito"] += 1 if caixa["classificacao"].get(e["id"], ("",))[0] == cl.SUSPEITO else 0
    linhas = []
    for remetente, g in por_remetente.items():
        achado = achados[remetente]
        suspeito = g["suspeito"] > g["emails"] / 2
        feita = feitas.get(remetente)
        situacao = ""
        if feita:
            quando = feita["feita_em"].strftime("%d/%m/%Y")
            situacao = f"Desinscrito em {quando}" if feita["status"] == "ok" else f"Falhou: {feita['mensagem']}"
        linhas.append({
            "remetente": remetente, "nome": g["nome"], "emails": g["emails"], "lidos": g["lidos"] / g["emails"],
            "metodo": achado["metodo"], "suspeito": suspeito, "https": achado["https"], "http": achado["http"],
            "como": "Suspeito: só bloquear" if suspeito else desinscricao.ROTULOS[achado["metodo"]],
            "situacao": situacao, "feito": bool(feita and feita["status"] == "ok"),
        })
    return sorted(linhas, key=lambda l: (-l["emails"], l["remetente"]))


def _executar(alvos):
    barra = st.progress(0.0, text="Cancelando inscrições…")
    ok = 0
    for n, alvo in enumerate(alvos, 1):
        resultado = desinscricao.desinscrever(alvo["https"])
        repo.gravar_desinscricao(alvo["remetente"], desinscricao.dominio_da_url(alvo["https"]), alvo["metodo"],
                                 resultado["ok"], resultado["status"], resultado["mensagem"])
        ok += resultado["ok"]
        barra.progress(n / len(alvos), text=f"{n} de {len(alvos)}")
    dados.renovar_tabelas()
    texto = f"{ok} de {len(alvos)} {'inscrição cancelada' if len(alvos) == 1 else 'inscrições canceladas'}."
    if ok != len(alvos):
        texto += " Os que falharam têm o motivo na coluna Situação; abra o link à mão."
    st.session_state.tri_aviso = ("sucesso" if ok == len(alvos) else "erro", texto)


@st.dialog("Desinscrever com um clique")
def _dialogo(alvos):
    dominios = sorted({desinscricao.dominio_da_url(a["https"]) for a in alvos})
    st.markdown(
        f"O ATLAS vai pedir o cancelamento a **{fmt_int(len(alvos))} {'remetente' if len(alvos) == 1 else 'remetentes'}** "
        f"({', '.join(dominios[:6])}"
        f"{'…' if len(dominios) > 6 else ''}). É o pedido de um clique do próprio remetente, em HTTPS. O ATLAS não abre "
        "a página nem segue redirecionamentos, e só fala com endereços públicos. Os e-mails já recebidos ficam como estão.")
    esquerda, direita = st.columns(2)
    if esquerda.button("Cancelar", key="tri_dlg_des_cancelar", width="stretch"):
        st.rerun()
    if direita.button("Desinscrever", key="tri_dlg_des_ok", type="primary", width="stretch"):
        _executar(alvos)
        st.rerun()


def secao():
    caixa = dados.caixa(dados.versao())
    achados = desinscricao.por_remetente(dados.cabecalhos_de_lista(dados.versao()))
    feitas = repo.listar_desinscricoes()
    linhas = _linhas(caixa, achados, feitas)
    with st.container(key="tri_card_desinscrever"):
        st.markdown(
            '<div class="tri-card-titulo">Desinscrever</div>'
            '<div class="tri-texto">Remetentes de lista, do maior volume para o menor. "Um clique" cancela pelo pedido do '
            'próprio remetente. "Só link" você abre à mão. Quem é suspeito nunca é desinscrito (isso confirmaria que o '
            'e-mail existe): bloqueie. Cancelar por e-mail exigiria a permissão de envio do Gmail, que não está ativada.'
            '</div>', unsafe_allow_html=True)
        esconder = st.toggle("Esconder quem já foi desinscrito", value=True, key="tri_esconder_desinscritos")
        visiveis = [l for l in linhas if not (esconder and l["feito"])]
        if not visiveis:
            st.markdown('<div class="tri-texto tri-vazio">Nenhum remetente de lista para mostrar.</div>',
                        unsafe_allow_html=True)
            return
        tabela = pd.DataFrame({
            "Nome": [l["nome"] for l in visiveis], "Remetente": [l["remetente"] for l in visiveis],
            "E-mails": [l["emails"] for l in visiveis], "Lidos": [l["lidos"] for l in visiveis],
            "Como": [l["como"] for l in visiveis], "Situação": [l["situacao"] for l in visiveis],
        })
        evento = st.dataframe(
            tabela, hide_index=True, width="stretch", height=min(520, 50 + 35 * len(tabela)), on_select="rerun",
            selection_mode="multi-row", key=dados.chave_tabela("tri_tabela_desinscrever"),
            column_config={
                "Nome": st.column_config.TextColumn(width=120), "Remetente": st.column_config.TextColumn(width=200),
                "E-mails": st.column_config.NumberColumn(format="%d", width=70),
                "Lidos": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent", width=90),
                "Como": st.column_config.TextColumn(width=200), "Situação": st.column_config.TextColumn(width="medium")})
        escolhidos = [visiveis[i] for i in evento.selection.rows]
        um_clique = [l for l in escolhidos if l["metodo"] == desinscricao.UM_CLIQUE and not l["suspeito"]]
        so_link = [l for l in escolhidos if l["metodo"] == desinscricao.LINK and not l["suspeito"]]
        if st.button(f"Desinscrever com um clique ({fmt_int(len(um_clique))})", key="tri_desinscrever",
                     type="primary", icon=":material/unsubscribe:", disabled=not um_clique):
            _dialogo(um_clique)
        for l in so_link[:MAX_LINKS_ABERTOS]:
            url = l["https"] or l["http"]
            st.link_button(f"Abrir a página de cancelamento de {desinscricao.dominio_da_url(url)}", url,
                           icon=":material/open_in_new:", key=f"tri_abrir_link_{l['remetente']}")
        if len(so_link) > MAX_LINKS_ABERTOS:
            st.markdown(f'<div class="tri-nota">Mostrando {MAX_LINKS_ABERTOS} de {len(so_link)} links; selecione menos '
                        'remetentes para ver os outros.</div>', unsafe_allow_html=True)
        pulados = len(escolhidos) - len(um_clique) - len(so_link)
        if pulados:
            st.markdown(f'<div class="tri-nota">{escape(str(pulados))} selecionados não entram aqui: são suspeitos ou '
                        'só têm opção por e-mail.</div>', unsafe_allow_html=True)
