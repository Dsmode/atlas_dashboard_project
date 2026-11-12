"""Editor de cards configuráveis: critérios E, OU e NÃO com prévia ao vivo."""
import itertools
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import classificacao as cl
from database.triagem import regras, repo
from database.triagem.estado import fmt_int

from . import dados

CORES = {"teal": "#2dd4bf", "purple": "#b44cff", "blue": "#5aa9ff", "green": "#4ade80", "lilac": "#c4b5fd"}
NOMES_CORES = {"teal": "Turquesa", "purple": "Roxo", "blue": "Azul", "green": "Verde", "lilac": "Lilás"}
_UIDS = itertools.count(1)
MAX_AMOSTRA = 12


def _linha(operador="ou", campo="texto", valor=""):
    return {"uid": next(_UIDS), "operador": operador, "campo": campo, "valor": valor}


def novo(nome="", criterios=None):
    """Abre o editor com um card novo, opcionalmente já preenchido (a partir de termos)."""
    st.session_state.tri_rascunho = {
        "id": None, "nome": nome, "cor": "teal", "entra": False,
        "criterios": [_linha(**c) for c in (criterios or [])] or [_linha()],
    }
    st.session_state.pop("tri_aberto", None)


def editar(card):
    st.session_state.tri_rascunho = {
        "id": card["id"], "nome": card["nome"], "cor": card["cor"], "entra": card["entra_no_resumo"],
        "criterios": [_linha(**c) for c in card["criterios"]] or [_linha()],
    }
    st.session_state.pop("tri_aberto", None)


def card_a_partir_de_termos(termos, nome=None):
    """Callback de botão: abre o editor com um critério OU (assunto ou trecho) para cada termo."""
    novo(nome or termos[0].capitalize(), [{"operador": "ou", "campo": "texto", "valor": t} for t in termos])
    st.session_state.tri_secao = "Cards"


def _fechar():
    st.session_state.pop("tri_rascunho", None)
    for chave in [k for k in st.session_state if str(k).startswith("tri_c_") or k in ("tri_ed_nome", "tri_ed_cor",
                                                                                    "tri_ed_resumo")]:
        st.session_state.pop(chave, None)


def _sincronizar(rascunho):
    """Traz para o rascunho o que está nos campos agora. Os botões rodam como callback, antes de a tela ser
    redesenhada, e os valores que o usuário acabou de digitar só existem em `st.session_state`."""
    ss = st.session_state
    rascunho["nome"] = ss.get("tri_ed_nome", rascunho["nome"])
    rascunho["cor"] = ss.get("tri_ed_cor") or rascunho["cor"]
    rascunho["entra"] = ss.get("tri_ed_resumo", rascunho["entra"])
    for c in rascunho["criterios"]:
        c["campo"] = ss.get(f"tri_c_{c['uid']}_campo", c["campo"])
        c["valor"] = ss.get(f"tri_c_{c['uid']}_valor_{c['campo']}", c["valor"])


def _adicionar(rascunho, operador):
    _sincronizar(rascunho)
    rascunho["criterios"].append(_linha(operador=operador))


def _remover(rascunho, uid):
    _sincronizar(rascunho)
    rascunho["criterios"] = [c for c in rascunho["criterios"] if c["uid"] != uid]


def _linha_criterio(rascunho, c):
    colunas = st.columns([5, 6, 1], vertical_alignment="bottom")
    campos = list(regras.CAMPOS)
    with colunas[0]:
        c["campo"] = st.selectbox("Campo", campos, index=campos.index(c["campo"]), key=f"tri_c_{c['uid']}_campo",
                                  format_func=lambda k: regras.CAMPOS[k][0], label_visibility="collapsed")
    fixos = regras.CAMPOS[c["campo"]][1]
    with colunas[1]:
        chave = f"tri_c_{c['uid']}_valor_{c['campo']}"
        if fixos:
            opcoes = list(fixos)
            c["valor"] = st.selectbox("Valor", opcoes, index=opcoes.index(c["valor"]) if c["valor"] in opcoes else 0,
                                      key=chave, format_func=fixos.get, label_visibility="collapsed")
        else:
            c["valor"] = st.text_input("Valor", value=c["valor"] if c["valor"] not in fixos_valores() else "",
                                       key=chave, placeholder="palavra, expressão ou endereço",
                                       label_visibility="collapsed")
    with colunas[2]:
        st.button("", key=f"tri_c_{c['uid']}_remover", icon=":material/close:", help="Remover critério",
                  on_click=_remover, args=(rascunho, c["uid"]))


def fixos_valores():
    return {v for _, fixos in regras.CAMPOS.values() if fixos for v in fixos}


def _grupo(rascunho, operador, titulo, ajuda):
    st.markdown(f'<div class="tri-secao-titulo">{titulo}</div><div class="tri-nota">{ajuda}</div>',
                unsafe_allow_html=True)
    for c in [c for c in rascunho["criterios"] if c["operador"] == operador]:
        _linha_criterio(rascunho, c)
    st.button("Adicionar critério", key=f"tri_c_add_{operador}", icon=":material/add:", on_click=_adicionar,
              args=(rascunho, operador))


def _previa(rascunho, caixa):
    st.markdown('<div class="tri-card-titulo">Prévia ao vivo</div>', unsafe_allow_html=True)
    criterios, erro = regras.validar(rascunho["criterios"])
    if erro:
        st.markdown(f'<div class="tri-texto tri-vazio">{escape(erro)}</div>', unsafe_allow_html=True)
        return criterios, erro
    ids = regras.ids_que_casam(criterios, caixa["preparados"])
    classe = caixa["classificacao"]
    excluidos = {i for i in ids if classe.get(i, ("",))[0] == cl.SUSPEITO}
    ids -= excluidos
    resumo = cl.resumo_de_ids(caixa["emails"], ids)
    st.markdown(
        f'<div class="tri-contagem"><strong>{fmt_int(resumo["emails"])}</strong>'
        f'<span>e-mails de {fmt_int(resumo["remetentes"])} remetentes casam com esta regra</span></div>',
        unsafe_allow_html=True)
    avisos = []
    protegidos = sum(1 for i in ids if classe.get(i, ("",))[0] == cl.PROTEGIDO)
    if protegidos:
        avisos.append(f"{fmt_int(protegidos)} de remetentes protegidos")
    if excluidos:
        avisos.append(f"{fmt_int(len(excluidos))} ficam de fora por serem suspeitos")
    outros = [f"{fmt_int(len([e for e in ids if e in c_ids]))} também em {nome}"
              for nome, c_ids in ((c["nome"], caixa["membros"][c["id"]]) for c in caixa["cards"]
                                  if c["id"] != rascunho["id"]) if ids & c_ids]
    if avisos or outros:
        st.markdown('<div class="tri-chips">' + "".join(
            f'<span class="tri-chip">{escape(a)}</span>' for a in [*avisos, *outros]) + "</div>", unsafe_allow_html=True)
    if ids:
        amostra = sorted((e for e in caixa["emails"] if e["id"] in ids), key=lambda e: e["data_email"] or 0,
                         reverse=True)[:MAX_AMOSTRA]
        st.dataframe(pd.DataFrame({
            "Assunto": [e["assunto"] or "(sem assunto)" for e in amostra],
            "Remetente": [e["remetente_email"] for e in amostra],
        }), hide_index=True, width="stretch", height=40 + 35 * len(amostra))
    return criterios, None


def _salvar(rascunho):
    _sincronizar(rascunho)
    criterios, erro = regras.validar(rascunho["criterios"])
    if erro or not rascunho["nome"].strip():
        st.session_state.tri_ed_erro = erro or "Dê um nome ao card."
        return
    repo.salvar_card(rascunho["id"], rascunho["nome"].strip(), rascunho["cor"], rascunho["entra"], criterios)
    st.session_state.pop("tri_ed_erro", None)
    _fechar()


def _excluir(card_id):
    repo.excluir_card(card_id)
    _fechar()


def secao():
    rascunho = st.session_state.tri_rascunho
    caixa = dados.caixa(dados.versao())
    st.button("Voltar aos cards", key="tri_ed_voltar", icon=":material/arrow_back:", on_click=_fechar)
    esquerda, direita = st.columns([3, 2], gap="large")
    with esquerda, st.container(key="tri_card_editor"):
        st.markdown(f'<div class="tri-card-titulo">{"Novo card" if rascunho["id"] is None else "Editar card"}</div>'
                    '<div class="tri-texto">Um e-mail casa quando todos os critérios <b>E</b> casam, pelo menos um '
                    '<b>OU</b> casa e nenhum <b>NÃO</b> casa. A regra vale mais que os sinais automáticos: quem casa '
                    'aqui não vai para Lixo nem Revisar. Suspeitos nunca entram.</div>', unsafe_allow_html=True)
        rascunho["nome"] = st.text_input("Nome do card", value=rascunho["nome"], key="tri_ed_nome", max_chars=60)
        rascunho["cor"] = st.segmented_control("Cor", list(CORES), default=rascunho["cor"], key="tri_ed_cor",
                                               format_func=NOMES_CORES.get) or rascunho["cor"]
        rascunho["entra"] = st.toggle("Entra no resumo (reservado para o resumo diário)", value=rascunho["entra"],
                                      key="tri_ed_resumo")
        _grupo(rascunho, "e", "Precisa ter tudo (E)", "Todos os critérios deste bloco precisam casar.")
        _grupo(rascunho, "ou", "Precisa ter pelo menos um (OU)", "Basta um critério deste bloco casar.")
        _grupo(rascunho, "nao", "Não pode ter (NÃO)", "Se qualquer critério deste bloco casar, o e-mail fica de fora.")
    with direita, st.container(key="tri_card_previa"):
        _, erro_regra = _previa(rascunho, caixa)

    with st.container(horizontal=True, gap="small", key="tri_ed_acoes"):
        st.button("Salvar card", key="tri_ed_salvar", type="primary", icon=":material/check:", disabled=bool(erro_regra),
                  on_click=_salvar, args=(rascunho,))
        if rascunho["id"] is not None:
            with st.popover("Excluir card", icon=":material/delete:"):
                st.markdown("Os e-mails não são afetados: só a regra some, e eles voltam a ser classificados pelos "
                            "sinais automáticos.")
                st.button("Excluir de vez", key="tri_ed_excluir", on_click=_excluir, args=(rascunho["id"],))
    if st.session_state.get("tri_ed_erro"):
        st.error(st.session_state.tri_ed_erro)
