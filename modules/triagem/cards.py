"""Seção "Cards": a grade (três cards fixos, cards do usuário e "Novo card"), a lista de remetentes de cada um, a
explicação por e-mail e a correção que ensina."""
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import automatico, limpeza, regras, repo
from database.triagem import classificacao as cl
from database.triagem.estado import fmt_int

from . import acoes, dados, editor

ICONES = {  # traços do conjunto Lucide (mesmo estilo do mockup aprovado)
    "trash": '<path d="M3 6h18M8 6V4h8v2m-9 0l1 14h8l1-14M10 11v6m4-6v6"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M12 8v4m0 3v.01"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "tag": '<path d="M20 13l-7 7-9-9V4h7z"/><circle cx="8.5" cy="8.5" r="1"/>',
}
CARDS = {
    cl.LIXO: {"titulo": "Lixo", "subtitulo": "Sinais automáticos", "icone": "trash", "tom": "lixo"},
    cl.SUSPEITO: {"titulo": "Spam e suspeitos", "subtitulo": "Alerta automático", "icone": "shield", "tom": "spam"},
    cl.REVISAR: {"titulo": "Revisar", "subtitulo": "O sistema ficou em dúvida", "icone": "eye", "tom": "revisar"},
}
NOMES_FIXOS = {cl.LIXO: "Lixo", cl.SUSPEITO: "Spam e suspeitos", cl.REVISAR: "Revisar", cl.PROTEGIDO: "Protegido"}
EXPLICACAO = {
    cl.LIXO: "Promoções e redes sociais que você nunca abriu (de quem oferece cancelar a inscrição) e remetentes "
             "que mandam muito e você quase não lê. E-mails com uma palavra que salva ficam em Revisar.",
    cl.SUSPEITO: "Marcados como spam pelo Gmail, com falha de autenticação (SPF, DKIM, DMARC) ou imitando o nome ou "
                 "o domínio de um remetente protegido.",
    cl.REVISAR: "E-mails não lidos que não casaram com nenhum sinal claro. Se o remetente é confiável, proteja-o.",
}
MAX_EMAILS_DO_REMETENTE = 100


def _icone(nome):
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICONES[nome]}</svg>')


def _plural(n, singular, plural):
    return f"{fmt_int(n)} {singular if n == 1 else plural}"


def _abrir(card):
    st.session_state.tri_aberto = card


def _voltar():
    st.session_state.pop("tri_aberto", None)


def _topo(resumo):
    return "".join(
        f'<li><span>{escape(remetente)}</span><span>{fmt_int(n)}</span></li>' for remetente, n in resumo["top"]
    ) or '<li class="tri-vazio"><span>Nenhum e-mail aqui.</span></li>'


def _cabecalho_tile(titulo, subtitulo, icone, resumo):
    return (
        f'<div class="tri-th"><div class="tri-ico">{_icone(icone)}</div>'
        f'<div><div class="tri-card-titulo">{escape(titulo)}</div><div class="tri-nota">{escape(subtitulo)}</div></div>'
        f'</div><div class="tri-contagem"><strong>{fmt_int(resumo["emails"])}</strong>'
        f'<span>{_plural(resumo["emails"], "e-mail", "e-mails")} de '
        f'{_plural(resumo["remetentes"], "remetente", "remetentes")}</span></div>'
        f'<ul class="tri-remetentes">{_topo(resumo)}</ul>')


def _modo_texto(modos, chave):
    return "Automático: " + automatico.MODOS[automatico.modo_do_card(modos, chave)].lower()


def _tile_fixo(card, resumo, modos):
    info, dados_card = CARDS[card], resumo[card]
    with st.container(key=f"tri_card_{info['tom']}"):
        st.markdown(_cabecalho_tile(info["titulo"], f"{info['subtitulo']} · {_modo_texto(modos, card).lower()}",
                                    info["icone"], dados_card),
                    unsafe_allow_html=True)
        st.button("Abrir", key=f"tri_abrir_{card}", icon=":material/arrow_forward:", on_click=_abrir, args=(card,),
                  disabled=not dados_card["emails"])


def _tile_usuario(card, resumo, modos):
    cor = editor.CORES.get(card["cor"], editor.CORES["teal"])
    subtitulo = (f"Regra sua · {_modo_texto(modos, automatico.chave_do_card(card['id'])).lower()}"
                 + (" · entra no resumo" if card["entra_no_resumo"] else ""))
    with st.container(key=f"tri_card_u{card['id']}"):
        st.markdown(f'<style>.st-key-tri_card_u{card["id"]}{{--tri-cor:{cor};}}</style>'
                    + _cabecalho_tile(card["nome"], subtitulo, "tag", resumo), unsafe_allow_html=True)
        with st.container(horizontal=True, gap="small"):
            st.button("Abrir", key=f"tri_abrir_u{card['id']}", icon=":material/arrow_forward:", on_click=_abrir,
                      args=(card["id"],), disabled=not resumo["emails"])
            st.button("Editar regra", key=f"tri_editar_u{card['id']}", on_click=editor.editar, args=(card,))


def _tile_novo():
    with st.container(key="tri_card_novo"):
        st.markdown('<div class="tri-card-titulo">Novo card</div><div class="tri-texto">Crie uma regra com critérios '
                    'E, OU e NÃO, com prévia ao vivo. Também dá para partir de um grupo de termos.</div>',
                    unsafe_allow_html=True)
        st.button("Criar card", key="tri_novo_card", type="primary", icon=":material/add:", on_click=editor.novo)


def _grade(caixa):
    modos = repo.obter_modos()
    tiles = [(_tile_fixo, (c, caixa["resumo"], modos)) for c in CARDS]
    tiles += [(_tile_usuario, (c, caixa["resumo_cards"][c["id"]], modos)) for c in caixa["cards"]]
    tiles.append((_tile_novo, ()))
    for inicio in range(0, len(tiles), 3):
        for coluna, (desenhar, args) in zip(st.columns(3), tiles[inicio:inicio + 3], strict=False):
            with coluna:
                desenhar(*args)
    protegidos = caixa["resumo"][cl.PROTEGIDO]
    st.markdown(
        f'<div class="tri-nota">{_plural(protegidos["emails"], "e-mail", "e-mails")} de '
        f'{_plural(protegidos["remetentes"], "remetente protegido", "remetentes protegidos")} ficam fora de Lixo e '
        'Revisar. Prioridade: spam e suspeitos, depois protegidos, depois as regras dos seus cards, depois os sinais '
        'automáticos. Um e-mail pode estar em vários cards seus.</div>', unsafe_allow_html=True)


# ---------- lista de remetentes de um card ----------

def _proteger(linhas, indices, por):
    itens = []
    for i in indices:
        remetente, dominio = linhas[i]["remetente"], linhas[i]["dominio"]
        itens.append(("email", remetente) if por == "email" else ("dominio", dominio))
    repo.adicionar_protegidos([i for i in itens if i[1] and i[1] != "(sem remetente)"])


def _ensinar(remetentes, card_id, operador):
    """A correção ensina: o remetente entra (OU) ou sai (NÃO) da regra do card, por e-mail exato."""
    for remetente in remetentes:
        repo.adicionar_criterio(card_id, operador, "email", remetente)
    dados.renovar_tabelas()


def _por_que_do_email(caixa, e):
    partes = []
    fixo = caixa["classificacao"].get(e["id"])
    if fixo:
        partes.append(f"{NOMES_FIXOS[fixo[0]]}: {fixo[1]}")
    for c in caixa["cards"]:
        if e["id"] in caixa["membros"][c["id"]]:
            partes.append(f"{c['nome']}: " + "; ".join(regras.motivos(c["criterios"], caixa["preparados"][e["id"]])))
    return " | ".join(partes) or "Fora de todos os cards (lido ou sem sinal)"


def _emails_do_remetente(caixa, remetente):
    """Por que cada e-mail do remetente caiu onde caiu."""
    st.markdown(f'<div class="tri-secao-titulo">E-mails de {escape(remetente)}</div>', unsafe_allow_html=True)
    emails = sorted((e for e in caixa["emails"] if (e["remetente_email"] or "").lower() == remetente and not e["enviado"]),
                    key=lambda e: e["data_email"] or 0, reverse=True)
    mostrados = emails[:MAX_EMAILS_DO_REMETENTE]
    st.dataframe(
        pd.DataFrame({
            "Data": [e["data_email"].strftime("%d/%m/%Y") if e["data_email"] else "" for e in mostrados],
            "Assunto": [e["assunto"] or "(sem assunto)" for e in mostrados],
            "Lido": ["sim" if e["lido"] else "não" for e in mostrados],
            "Por quê": [_por_que_do_email(caixa, e) for e in mostrados],
        }), hide_index=True, width="stretch", height=min(420, 50 + 35 * len(mostrados)),
        column_config={"Data": st.column_config.TextColumn(width=90), "Lido": st.column_config.TextColumn(width=60),
                       "Assunto": st.column_config.TextColumn(width=260), "Por quê": st.column_config.TextColumn()})
    if len(emails) > len(mostrados):
        st.markdown(f'<div class="tri-nota">Mostrando os {MAX_EMAILS_DO_REMETENTE} mais recentes de '
                    f'{fmt_int(len(emails))}.</div>', unsafe_allow_html=True)


def _contexto_do_card(caixa, aberto):
    """(título, texto de apoio, tom do CSS, ids, função de motivo, card do usuário ou None)."""
    if aberto in CARDS:
        info = CARDS[aberto]
        ids = {i for i, (c, _) in caixa["classificacao"].items() if c == aberto}
        return info["titulo"], EXPLICACAO[aberto], info["tom"], ids, (lambda e: caixa["classificacao"][e["id"]][1]), None
    card = next(c for c in caixa["cards"] if c["id"] == aberto)
    regra = "; ".join(regras.descrever(c) for c in card["criterios"] if c["operador"] != "nao")
    return (card["nome"], f"Regra sua: {regra}.", f"u{aberto}", caixa["membros"][aberto],
            (lambda e: "; ".join(regras.motivos(card["criterios"], caixa["preparados"][e["id"]]))), card)


def _detalhe(aberto, caixa):
    titulo, apoio, tom, ids, motivo_de, card_usuario = _contexto_do_card(caixa, aberto)
    st.button("Voltar aos cards", key="tri_voltar", icon=":material/arrow_back:", on_click=_voltar)
    linhas = cl.remetentes_de(caixa["emails"], ids, motivo_de)
    with st.container(key=f"tri_card_{tom}_detalhe"):
        st.markdown(
            f'<div class="tri-card-titulo">{escape(titulo)}</div>'
            f'<div class="tri-texto">{_plural(len(ids), "e-mail", "e-mails")} de '
            f'{_plural(len(linhas), "remetente", "remetentes")}, do maior volume para o menor. {escape(apoio)}</div>',
            unsafe_allow_html=True)
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
            selection_mode="multi-row", key=dados.chave_tabela(f"tri_tabela_{aberto}"),
            column_config={
                "Nome": st.column_config.TextColumn(width=120),
                "Remetente": st.column_config.TextColumn(width=200),
                "E-mails": st.column_config.NumberColumn(format="%d", width=70),
                "Lidos": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent", width=90),
                "Por quê": st.column_config.TextColumn(width="large"),
            })
        escolhidos = list(evento.selection.rows)
        _acoes(caixa, aberto, linhas, escolhidos, card_usuario)
        _acoes_gmail(caixa, aberto, titulo, ids, motivo_de, linhas, escolhidos)
        if len(escolhidos) == 1:
            _emails_do_remetente(caixa, linhas[escolhidos[0]]["remetente"])
        else:
            st.markdown('<div class="tri-nota">Selecione um remetente para ver, e-mail por e-mail, por que cada um '
                        'caiu aqui.</div>', unsafe_allow_html=True)


def _acoes(caixa, aberto, linhas, escolhidos, card_usuario):
    remetentes = [linhas[i]["remetente"] for i in escolhidos]
    with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
        for rotulo, por, chave in (("Proteger remetente", "email", "tri_prot_email"),
                                   ("Proteger domínio", "dominio", "tri_prot_dominio")):
            if st.button(rotulo, key=chave, icon=":material/verified_user:", disabled=not escolhidos):
                _proteger(linhas, escolhidos, por)
                dados.renovar_tabelas()
                st.rerun()
        for rotulo, por, chave in (("Marcar como golpe", "email", "tri_golpe_email"),
                                   ("Bloquear domínio", "dominio", "tri_golpe_dominio")):
            if st.button(rotulo, key=chave, icon=":material/gpp_bad:", disabled=not escolhidos):
                acoes.marcar_como_golpe(linhas, escolhidos, por)
                st.rerun()
        if card_usuario:
            st.button("Tirar deste card", key="tri_tirar", icon=":material/remove_circle:", disabled=not escolhidos,
                      on_click=_ensinar, args=(remetentes, card_usuario["id"], "nao"))
    outros = [c for c in caixa["cards"] if not card_usuario or c["id"] != card_usuario["id"]]
    if outros:
        with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
            destino = st.selectbox("Mandar para o card", outros, format_func=lambda c: c["nome"], key="tri_destino",
                                   disabled=not escolhidos)
            st.button("Ensinar", key="tri_ensinar", icon=":material/school:", disabled=not escolhidos,
                      on_click=_ensinar, args=(remetentes, destino["id"], "ou"),
                      help="Acrescenta o e-mail do remetente como critério OU na regra do card escolhido.")
    st.markdown('<div class="tri-nota">Protegido não entra em Lixo nem em Revisar e não é movido em lote. Se o '
                'e-mail de um protegido falhar no DMARC, ele vai para Spam e suspeitos (pode ser forjado). "Ensinar" '
                'e "Tirar deste card" mudam a regra do card; você pode revisá-las em Editar regra.</div>',
                unsafe_allow_html=True)


def _acoes_gmail(caixa, aberto, titulo, ids, motivo_de, linhas, escolhidos):
    """Ações que mexem no Gmail. Marcar só etiqueta; arquivar e lixeira pedem confirmação."""
    nome = acoes.nome_do_marcador(aberto, caixa)
    remetentes = [linhas[i]["remetente"] for i in escolhidos]
    ids_escolhidos = acoes.ids_dos_remetentes(caixa, ids, remetentes)
    todos_ativos = aberto in (cl.LIXO, cl.SUSPEITO)  # a lixeira em bloco só vale onde o sinal é forte
    st.markdown('<div class="tri-secao-titulo">No Gmail</div><div class="tri-nota">Marcar só etiqueta, nada sai da '
                'caixa de entrada. Arquivar leva para a quarentena. Mover para a lixeira se desfaz em Histórico, por '
                'até 30 dias. Arquivar e mover para a lixeira nunca incluem remetentes protegidos.</div>', unsafe_allow_html=True)
    with st.container(horizontal=True, gap="small", vertical_alignment="bottom", key="tri_acoes_gmail"):
        with st.popover("Marcar no Gmail", icon=":material/label:"):
            st.markdown(f"Etiqueta os e-mails com **{escape(nome)}**.")
            if st.button(f"Marcar o card todo ({fmt_int(len(ids))})", key="tri_marcar_tudo", disabled=not ids):
                with st.spinner("Marcando no Gmail…"):
                    acoes.marcar_no_gmail(caixa, aberto, ids)
                st.rerun()
            if st.button(f"Marcar só os selecionados ({fmt_int(len(ids_escolhidos))})", key="tri_marcar_sel",
                         disabled=not ids_escolhidos):
                with st.spinner("Marcando no Gmail…"):
                    acoes.marcar_no_gmail(caixa, aberto, ids, ids_escolhidos)
                st.rerun()
        with st.popover("Arquivar", icon=":material/archive:"):
            st.markdown(f"Tira da caixa de entrada e põe em **{limpeza.QUARENTENA}**.")
            if st.button(f"Arquivar os selecionados ({fmt_int(len(ids_escolhidos))})", key="tri_arq_sel",
                         disabled=not ids_escolhidos):
                acoes.pedir_arquivar(caixa, ids_escolhidos, titulo)
            if st.button(f"Arquivar o card todo ({fmt_int(len(ids))})", key="tri_arq_tudo", disabled=not ids):
                acoes.pedir_arquivar(caixa, ids, titulo)
        with st.popover("Mover para a lixeira", icon=":material/delete:"):
            st.markdown("Vai para a lixeira do Gmail, com confirmação.")
            if st.button(f"Mover os selecionados ({fmt_int(len(ids_escolhidos))})", key="tri_lix_sel",
                         disabled=not ids_escolhidos):
                acoes.pedir_lixeira(caixa, ids_escolhidos, titulo)
            if todos_ativos and st.button(f"Mover o card todo ({fmt_int(len(ids))})", key="tri_lix_tudo",
                                          disabled=not ids):
                acoes.pedir_lixeira(caixa, ids, titulo)
        st.download_button("Exportar CSV", data=acoes.csv_do_card(caixa, titulo, ids, motivo_de),
                           file_name=f"atlas_{aberto if isinstance(aberto, str) else 'card_' + str(aberto)}.csv",
                           mime="text/csv", icon=":material/download:", key="tri_csv")


def secao():
    caixa = dados.caixa(dados.versao())
    if "tri_rascunho" in st.session_state:
        editor.secao()
        return
    if not caixa["emails"]:
        with st.container(key="tri_card_vazio"):
            st.markdown('<div class="tri-card-titulo">Os cards aparecem depois da importação</div>'
                        '<div class="tri-texto">Assim que os primeiros e-mails chegarem, eles são separados em '
                        'Lixo, Spam e suspeitos e Revisar. Você também poderá criar os seus.</div>',
                        unsafe_allow_html=True)
        return
    aberto = st.session_state.get("tri_aberto")
    if aberto in CARDS or aberto in {c["id"] for c in caixa["cards"]}:
        _detalhe(aberto, caixa)
    else:
        _grade(caixa)
