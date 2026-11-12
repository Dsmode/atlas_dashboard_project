"""Seção "Cards": a grade com os três cards fixos e a lista de remetentes de cada um."""
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import classificacao as cl
from database.triagem import repo
from database.triagem.estado import fmt_int

from . import dados

ICONES = {  # traços do conjunto Lucide (mesmo estilo do mockup aprovado)
    "trash": '<path d="M3 6h18M8 6V4h8v2m-9 0l1 14h8l1-14M10 11v6m4-6v6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M12 8v4m0 3v.01"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
}
CARDS = {
    cl.LIXO: {"titulo": "Lixo", "subtitulo": "Sinais automáticos", "icone": "trash", "tom": "lixo"},
    cl.SUSPEITO: {"titulo": "Spam e suspeitos", "subtitulo": "Alerta automático", "icone": "shield", "tom": "spam"},
    cl.REVISAR: {"titulo": "Revisar", "subtitulo": "O sistema ficou em dúvida", "icone": "eye", "tom": "revisar"},
}
EXPLICACAO = {
    cl.LIXO: "Promoções e redes sociais que você nunca abriu (de quem oferece cancelar a inscrição) e remetentes "
             "que mandam muito e você quase não lê.",
    cl.SUSPEITO: "Marcados como spam pelo Gmail, com falha de autenticação (SPF, DKIM, DMARC) ou imitando o nome ou "
                 "o domínio de um remetente protegido.",
    cl.REVISAR: "E-mails não lidos que não casaram com nenhum sinal claro. Se o remetente é confiável, proteja-o.",
}


def _icone(nome):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONES[nome]}</svg>'


def _plural(n, singular, plural):
    return f"{fmt_int(n)} {singular if n == 1 else plural}"


def _abrir(card):
    st.session_state.tri_aberto = card


def _voltar():
    st.session_state.pop("tri_aberto", None)


def _tile(card, resumo):
    info, dados_card = CARDS[card], resumo[card]
    topo = "".join(
        f'<li><span>{escape(remetente)}</span><span>{fmt_int(n)}</span></li>' for remetente, n in dados_card["top"]
    ) or '<li class="tri-vazio"><span>Nenhum e-mail aqui.</span></li>'
    with st.container(key=f"tri_card_{info['tom']}"):
        st.markdown(
            f'<div class="tri-th"><div class="tri-ico">{_icone(info["icone"])}</div>'
            f'<div><div class="tri-card-titulo">{info["titulo"]}</div>'
            f'<div class="tri-nota">{info["subtitulo"]}</div></div></div>'
            f'<div class="tri-contagem"><strong>{fmt_int(dados_card["emails"])}</strong>'
            f'<span>{_plural(dados_card["emails"], "e-mail", "e-mails")} de '
            f'{_plural(dados_card["remetentes"], "remetente", "remetentes")}</span></div>'
            f'<ul class="tri-remetentes">{topo}</ul>', unsafe_allow_html=True)
        st.button("Abrir", key=f"tri_abrir_{card}", icon=":material/arrow_forward:", on_click=_abrir, args=(card,),
                  disabled=not dados_card["emails"])


def _grade(caixa):
    colunas = st.columns(3)
    for coluna, card in zip(colunas, CARDS, strict=True):
        with coluna:
            _tile(card, caixa["resumo"])
    protegidos = caixa["resumo"][cl.PROTEGIDO]
    st.markdown(
        f'<div class="tri-nota">{_plural(protegidos["emails"], "e-mail", "e-mails")} de '
        f'{_plural(protegidos["remetentes"], "remetente protegido", "remetentes protegidos")} ficam fora dos cards. '
        'Um e-mail só cai em um card; as regras que você criar entrarão antes dos sinais automáticos.</div>',
        unsafe_allow_html=True)


def _proteger(linhas, indices, por):
    itens = []
    for i in indices:
        remetente, dominio = linhas[i]["remetente"], linhas[i]["dominio"]
        itens.append(("email", remetente) if por == "email" else ("dominio", dominio))
    repo.adicionar_protegidos([i for i in itens if i[1] and i[1] != "(sem remetente)"])


def _detalhe(card, caixa):
    info = CARDS[card]
    st.button("Voltar aos cards", key="tri_voltar", icon=":material/arrow_back:", on_click=_voltar)
    linhas = cl.remetentes_do_card(caixa["emails"], caixa["classificacao"], card)
    total = sum(l["emails"] for l in linhas)
    with st.container(key=f"tri_card_{info['tom']}_detalhe"):
        st.markdown(
            f'<div class="tri-card-titulo">{info["titulo"]}</div>'
            f'<div class="tri-texto">{_plural(total, "e-mail", "e-mails")} de {_plural(len(linhas), "remetente", "remetentes")}, '
            f'do maior volume para o menor. {EXPLICACAO[card]}</div>', unsafe_allow_html=True)
        if not linhas:
            st.markdown('<div class="tri-texto tri-vazio">Nenhum e-mail neste card.</div>', unsafe_allow_html=True)
            return
        tabela = pd.DataFrame({
            "Nome": [l["nome"] for l in linhas], "Remetente": [l["remetente"] for l in linhas],
            "E-mails": [l["emails"] for l in linhas], "Lidos": [l["lidos"] for l in linhas],
            "Por quê": [l["motivo"] for l in linhas],
        })
        evento = st.dataframe(
            tabela, hide_index=True, width="stretch", height=min(560, 50 + 35 * len(tabela)), on_select="rerun",
            selection_mode="multi-row", key=dados.chave_tabela(f"tri_tabela_{card}"),
            column_config={
                "Nome": st.column_config.TextColumn(width=120),
                "Remetente": st.column_config.TextColumn(width=200),
                "E-mails": st.column_config.NumberColumn(format="%d", width=70),
                "Lidos": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent", width=90),
                "Por quê": st.column_config.TextColumn(width="large"),
            })
        escolhidos = list(evento.selection.rows)
        if card == cl.SUSPEITO:
            st.markdown('<div class="tri-nota">Marcar como golpe e mover para a lixeira chegam na próxima etapa. '
                        'Por enquanto, confira os motivos. Se for um engano, selecione e proteja o remetente.</div>',
                        unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small"):
            for rotulo, por, chave in (("Proteger remetente", "email", "tri_prot_email"),
                                       ("Proteger domínio", "dominio", "tri_prot_dominio")):
                if st.button(rotulo, key=chave, icon=":material/verified_user:", disabled=not escolhidos):
                    _proteger(linhas, escolhidos, por)
                    dados.renovar_tabelas()
                    st.rerun()
        st.markdown('<div class="tri-nota">Protegido não entra em Lixo nem em Revisar e não é movido em lote. '
                    'Se o e-mail de um protegido falhar na verificação DMARC, ele continua indo para Spam e '
                    'suspeitos (pode ser forjado).</div>', unsafe_allow_html=True)


def secao():
    caixa = dados.caixa(dados.versao())
    if not caixa["emails"]:
        with st.container(key="tri_card_vazio"):
            st.markdown('<div class="tri-card-titulo">Os cards aparecem depois da importação</div>'
                        '<div class="tri-texto">Assim que os primeiros e-mails chegarem, eles são separados em '
                        'Lixo, Spam e suspeitos e Revisar.</div>', unsafe_allow_html=True)
        return
    aberto = st.session_state.get("tri_aberto")
    if aberto in CARDS:
        _detalhe(aberto, caixa)
    else:
        _grade(caixa)
