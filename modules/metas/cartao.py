from html import escape

import streamlit as st

from components.checklist_sortable import checklist_sortable
from database.dinheiro import fmt_brl
from database.metas import repo
from database.metas.modelo import PRIORIDADES
from database.metas.progresso import fmt_qtd, progresso, ritmo
from modules.metas.controles import controle_quantidade, controle_valor
from modules.metas.dialogo import abrir_dialogo, pedir_exclusao
from modules.metas.regras import STATUS_EXIBIDO, situacao
from modules.metas.visual import chips, fmt_data
from modules.ui import script

LIMITE_DESCRICAO = 300


def _checklist(meta_id, tarefas):
    """Marcar e reordenar. Cada evento do componente grava na hora."""
    itens = [
        {"id": t["id"], "descricao": t["descricao"], "prazo": fmt_data(t["prazo"]) if t["prazo"] else "",
         "concluida": bool(t["concluida"])}
        for t in tarefas
    ]
    evento = checklist_sortable(itens, key=f"checklist_{meta_id}")
    if not evento or st.session_state.get(f"chk_evento_{meta_id}") == evento["id"]:
        return
    st.session_state[f"chk_evento_{meta_id}"] = evento["id"]
    if evento["evento"] == "toggle":
        repo.definir_tarefa_concluida(evento["tarefa_id"], evento["concluida"])
    else:
        repo.definir_ordem_tarefas(evento["ordem"])
    st.rerun()


def recolher_cartoes():
    """Ao trocar de módulo, descrições e checklists voltam a ficar recolhidos, como ao recarregar a página."""
    st.session_state.pop("descricoes_abertas", None)
    st.session_state.pop("checklists_abertos", None)


def disparar_confete():
    """Registra a posição do ✓ a cada clique e, se uma meta acabou de ser concluída, solta o confete uma vez só."""
    st.html(script("armar_confete"), unsafe_allow_javascript=True)
    if st.session_state.pop("confete", False):
        st.html(script("confete"), unsafe_allow_javascript=True)


def _concluir(meta_id):
    repo.definir_status(meta_id, "concluida")
    st.session_state["confete"] = True
    st.rerun()


def _acoes(meta, tarefas, atingida=False):
    """Editar, concluir ou reativar, arquivar e excluir. Numa meta atingida o ✓ ganha chave própria (brilho neon
    no CSS) e a dica avisa que já dá para concluir."""
    with st.container(horizontal=True, gap="xsmall", width="content", key=f"meta_actions_{meta['id']}"):
        if st.button("", icon=":material/edit:", key=f"edit_{meta['id']}", help="Editar"):
            abrir_dialogo(meta, tarefas)
        if meta["status"] == "ativa":
            if st.button(
                "", icon=":material/check:", key=f"conc_ok_{meta['id']}" if atingida else f"conc_{meta['id']}",
                help="Meta atingida! Concluir?" if atingida else "Concluir meta",
            ):
                _concluir(meta["id"])
            if st.button("", icon=":material/inventory_2:", key=f"arq_{meta['id']}", help="Arquivar"):
                repo.definir_status(meta["id"], "arquivada")
                st.rerun()
        elif st.button("", icon=":material/replay:", key=f"reat_{meta['id']}", help="Reativar"):
            repo.definir_status(meta["id"], "ativa")
            st.rerun()
        if st.button("", icon=":material/delete:", key=f"del_{meta['id']}", help="Excluir"):
            pedir_exclusao(meta["id"], meta["titulo"])


def _rotulo_progresso(meta, prog):
    tipo = meta["tipo_progresso"]
    if tipo == "tarefas":
        return "Tarefas", f"{prog['atual']} / {prog['alvo']}"
    if tipo == "valor":
        return "Valor", f"{fmt_brl(prog['atual'])} / {fmt_brl(prog['alvo'])}"
    unidade = f" {escape(meta['unidade'])}" if meta["unidade"] else ""
    return "Quantidade", f"{fmt_qtd(prog['atual'])} / {fmt_qtd(prog['alvo'])}{unidade}"


def _descricao(meta):
    """Descrição longa fica em 3 linhas com Ver mais / Ver menos. O Streamlit não mede linhas no servidor, então o
    corte é por quantidade de caracteres (LIMITE_DESCRICAO)."""
    texto = meta["descricao"]
    if not texto:
        return
    longa = len(texto) > LIMITE_DESCRICAO
    abertas = st.session_state.setdefault("descricoes_abertas", set())
    aberta = meta["id"] in abertas
    st.markdown(
        f'<p class="meta-desc{" clamp" if longa and not aberta else ""}">{escape(texto)}</p>',
        unsafe_allow_html=True,
    )
    if longa and st.button("Ver menos" if aberta else "Ver mais", key=f"desc_toggle_{meta['id']}"):
        abertas.symmetric_difference_update({meta["id"]})
        st.rerun()


def _informacoes_html(meta, prog, atrasada):
    rotulo, contagem = _rotulo_progresso(meta, prog)
    saldo_negativo = meta["tipo_progresso"] == "valor" and prog["atual"] < 0
    return (
        '<div class="meta-info">'
        f'<span class="meta-item{" late" if atrasada else ""}">'
        f'<span class="material-icon">{"event_busy" if atrasada else "calendar_today"}</span>'
        f'Prazo: {fmt_data(meta["prazo"])}</span>'
        f'<span class="meta-item prio-{meta["prioridade"]}">'
        f'<span class="material-icon">flag</span>Prioridade {PRIORIDADES[meta["prioridade"]]}</span></div>'
        f'<div class="prog-head"><span>{escape(rotulo)}</span>'
        f'<b class="{"prog-neg" if saldo_negativo else ""}">{contagem}</b></div>'
        f'<div class="prog-track"><div class="prog-fill" style="width:{prog["pct"]}%"></div></div>'
        f'<div class="prog-foot">{prog["pct"]}% concluído'
        f'{"<span class=prog-neg> · Saldo negativo</span>" if saldo_negativo else ""}</div>'
    )


def _bloco_checklist(meta, tarefas):
    if meta["tipo_progresso"] != "tarefas" or not tarefas:
        return
    # O aberto ou fechado fica em session_state porque o st.expander recolhe a cada rerun.
    abertos = st.session_state.setdefault("checklists_abertos", set())
    aberto = meta["id"] in abertos
    feitas = sum(1 for t in tarefas if t["concluida"])
    if st.button(
        f"Checklist ({feitas}/{len(tarefas)})", key=f"toggle_check_{meta['id']}", width="stretch",
        icon=":material/expand_less:" if aberto else ":material/expand_more:",
    ):
        abertos.symmetric_difference_update({meta["id"]})
        st.rerun()
    if aberto:
        _checklist(meta["id"], tarefas)


def cartao(meta, tarefas, hoje):
    prog = progresso(meta, tarefas)
    atingida = meta["status"] == "ativa" and prog["atingida"]
    estado = situacao(meta, hoje)

    with st.container(border=True, key=f"meta_card_{meta['id']}"):
        with st.container(horizontal=True, vertical_alignment="top", key=f"meta_head_{meta['id']}"):
            st.markdown(
                f'<p class="meta-title">{escape(meta["titulo"])}'
                f'<span class="badge status-{estado}">{STATUS_EXIBIDO[estado]}</span></p>{chips(meta["categorias"])}',
                unsafe_allow_html=True, width="stretch",
            )
            _acoes(meta, tarefas, atingida)

        _descricao(meta)
        st.markdown(_informacoes_html(meta, prog, estado == "atrasada"), unsafe_allow_html=True)

        texto_ritmo = ritmo(meta, hoje)
        if texto_ritmo:
            st.markdown(
                f'<div class="meta-ritmo"><span class="material-icon">schedule</span>{escape(texto_ritmo)}</div>',
                unsafe_allow_html=True,
            )

        if meta["tipo_progresso"] == "quantidade":
            controle_quantidade(meta)
        elif meta["tipo_progresso"] == "valor":
            controle_valor(meta)
        _bloco_checklist(meta, tarefas)
