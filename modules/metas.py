from datetime import date, timedelta

import streamlit as st

from database import metas_repo as repo

PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}
PRIORIDADE_ORDEM = {"alta": 0, "media": 1, "baixa": 2}
STATUS = {"ativa": "Ativa", "concluida": "Concluída", "arquivada": "Arquivada"}
STATUS_ORDEM = {"ativa": 0, "concluida": 1, "arquivada": 2}

VISOES = ["semana", "mes", "atrasadas", "sem_prazo"]
VISOES_NOME = {"semana": "Semanal", "mes": "Mensal", "atrasadas": "Atrasadas", "sem_prazo": "Sem prazo"}


def _fmt_data(d):
    return d.strftime("%d/%m/%Y") if d else "sem prazo"


def _intervalo_semana(hoje):
    ini = hoje - timedelta(days=hoje.weekday())
    return ini, ini + timedelta(days=6)


def _intervalo_mes(hoje):
    ini = hoje.replace(day=1)
    proximo = (ini + timedelta(days=32)).replace(day=1)
    return ini, proximo - timedelta(days=1)


def _atrasada(meta, hoje):
    return meta["status"] == "ativa" and meta["prazo"] is not None and meta["prazo"] < hoje


def _filtrar(metas, visao, hoje):
    if visao == "semana":
        ini, fim = _intervalo_semana(hoje)
        return [m for m in metas if m["prazo"] and ini <= m["prazo"] <= fim]
    if visao == "mes":
        ini, fim = _intervalo_mes(hoje)
        return [m for m in metas if m["prazo"] and ini <= m["prazo"] <= fim]
    if visao == "atrasadas":
        return [m for m in metas if _atrasada(m, hoje)]
    return [m for m in metas if m["prazo"] is None]


def _ordenar(metas):
    return sorted(
        metas,
        key=lambda m: (
            STATUS_ORDEM[m["status"]],
            m["prazo"] or date.max,
            PRIORIDADE_ORDEM[m["prioridade"]],
        ),
    )


# ---------- diálogos ----------

def _form_meta(meta=None):
    with st.form("form_meta", border=False):
        titulo = st.text_input("Título", value=meta["titulo"] if meta else "", max_chars=150)
        descricao = st.text_area("Descrição", value=(meta["descricao"] or "") if meta else "")
        col1, col2 = st.columns(2)
        prioridade = col1.selectbox(
            "Prioridade",
            list(PRIORIDADES),
            index=list(PRIORIDADES).index(meta["prioridade"]) if meta else 1,
            format_func=PRIORIDADES.get,
        )
        prazo = col2.date_input("Prazo (opcional)", value=meta["prazo"] if meta else None, format="DD/MM/YYYY")
        if st.form_submit_button("Salvar", type="primary", use_container_width=True):
            if not titulo.strip():
                st.error("O título é obrigatório.")
                return
            if meta:
                repo.atualizar_meta(meta["id"], titulo.strip(), descricao.strip() or None, prioridade, prazo)
            else:
                repo.criar_meta(titulo.strip(), descricao.strip() or None, prioridade, prazo)
            st.rerun()


@st.dialog("Nova meta")
def _dialogo_nova_meta():
    _form_meta()


@st.dialog("Editar meta")
def _dialogo_editar_meta(meta):
    _form_meta(meta)


@st.dialog("Confirmar exclusão")
def _dialogo_excluir(tipo, item_id, nome):
    aviso = " Todas as tarefas dela também serão apagadas." if tipo == "meta" else ""
    st.write(f"Excluir **{nome}**?{aviso}")
    col1, col2 = st.columns(2)
    if col1.button("Cancelar", use_container_width=True):
        st.rerun()
    if col2.button("Excluir", type="primary", use_container_width=True):
        _excluir(tipo, item_id)
        st.rerun()


def _excluir(tipo, item_id):
    if tipo == "meta":
        repo.excluir_meta(item_id)
    else:
        repo.excluir_tarefa(item_id)


def _pedir_exclusao(tipo, item_id, nome):
    if st.session_state.get("confirmar_exclusao", True):
        _dialogo_excluir(tipo, item_id, nome)
    else:
        _excluir(tipo, item_id)
        st.rerun()


# ---------- cartão da meta ----------

def _alternar_tarefa(tarefa_id):
    repo.definir_tarefa_concluida(tarefa_id, st.session_state[f"tarefa_{tarefa_id}"])


def _checklist(meta, tarefas):
    for t in tarefas:
        col_chk, col_prazo, col_del = st.columns([6, 2, 1], vertical_alignment="center")
        col_chk.checkbox(
            t["descricao"], value=bool(t["concluida"]), key=f"tarefa_{t['id']}",
            on_change=_alternar_tarefa, args=(t["id"],),
        )
        col_prazo.caption(_fmt_data(t["prazo"]) if t["prazo"] else "")
        if col_del.button("", icon=":material/close:", key=f"del_tarefa_{t['id']}", help="Excluir tarefa"):
            _pedir_exclusao("tarefa", t["id"], t["descricao"])

    with st.form(f"nova_tarefa_{meta['id']}", clear_on_submit=True, border=False):
        c1, c2, c3 = st.columns([5, 2, 1], vertical_alignment="bottom")
        descricao = c1.text_input("Nova tarefa", label_visibility="collapsed", placeholder="Nova tarefa...")
        prazo = c2.date_input("Prazo", value=None, label_visibility="collapsed", format="DD/MM/YYYY",
                              help="Prazo da tarefa (opcional)")
        if c3.form_submit_button("", icon=":material/add:", use_container_width=True) and descricao.strip():
            repo.criar_tarefa(meta["id"], descricao.strip(), prazo)
            st.rerun()


def _cartao(meta, tarefas, hoje):
    total = len(tarefas)
    feitas = sum(1 for t in tarefas if t["concluida"])
    pct = round(feitas / total * 100) if total else 0

    with st.container(border=True, key=f"meta_card_{meta['id']}"):
        topo, acoes = st.columns([5, 3], vertical_alignment="top")
        with topo:
            atrasada = '<span class="badge atrasada">Atrasada</span>' if _atrasada(meta, hoje) else ""
            st.markdown(
                f'<p class="meta-title">{meta["titulo"]}</p>'
                f'<span class="badge {meta["prioridade"]}">{PRIORIDADES[meta["prioridade"]]}</span>'
                f'<span class="badge status-{meta["status"]}">{STATUS[meta["status"]]}</span>'
                f'{atrasada}<span class="badge">{_fmt_data(meta["prazo"])}</span>',
                unsafe_allow_html=True,
            )
        with acoes:
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("", icon=":material/edit:", key=f"edit_{meta['id']}", help="Editar", use_container_width=True):
                _dialogo_editar_meta(meta)
            if meta["status"] == "ativa":
                if b2.button("", icon=":material/check:", key=f"conc_{meta['id']}", help="Concluir meta", use_container_width=True):
                    repo.definir_status(meta["id"], "concluida")
                    st.rerun()
                if b3.button("", icon=":material/inventory_2:", key=f"arq_{meta['id']}", help="Arquivar", use_container_width=True):
                    repo.definir_status(meta["id"], "arquivada")
                    st.rerun()
            elif b2.button("", icon=":material/replay:", key=f"reat_{meta['id']}", help="Reativar", use_container_width=True):
                repo.definir_status(meta["id"], "ativa")
                st.rerun()
            if b4.button("", icon=":material/delete:", key=f"del_{meta['id']}", help="Excluir", use_container_width=True):
                _pedir_exclusao("meta", meta["id"], meta["titulo"])

        if meta["descricao"]:
            st.markdown(f'<p class="meta-desc">{meta["descricao"]}</p>', unsafe_allow_html=True)

        st.progress(pct / 100, text=f"{feitas}/{total} tarefas · {pct}%" if total else "Sem tarefas ainda")

        # Estado de aberto/fechado em session_state: st.expander recolhe a cada rerun.
        abertos = st.session_state.setdefault("checklists_abertos", set())
        aberto = meta["id"] in abertos
        if st.button(
            f"Checklist ({feitas}/{total})", key=f"toggle_check_{meta['id']}",
            icon=":material/expand_less:" if aberto else ":material/expand_more:",
        ):
            abertos.symmetric_difference_update({meta["id"]})
            st.rerun()
        if aberto:
            _checklist(meta, tarefas)


# ---------- tela ----------

def render():
    hoje = date.today()
    metas = repo.listar_metas()
    tarefas_por_meta = {}
    for t in repo.listar_tarefas():
        tarefas_por_meta.setdefault(t["meta_id"], []).append(t)

    topo, botao = st.columns([3, 2], vertical_alignment="center")
    topo.markdown('<div class="atlas-title">Metas Pessoais</div>', unsafe_allow_html=True)
    if botao.button("Nova meta", icon=":material/add:", type="primary", use_container_width=True):
        _dialogo_nova_meta()

    contagem = {v: len(_filtrar(metas, v, hoje)) for v in VISOES}
    visao = st.segmented_control(
        "Visualização", VISOES, default="semana", key="visao_metas",
        format_func=lambda v: f"{VISOES_NOME[v]} ({contagem[v]})", label_visibility="collapsed",
    ) or "semana"

    # Estado guardado à parte: widgets perdem o valor ao trocar de módulo.
    st.toggle(
        "Confirmar exclusões",
        value=st.session_state.get("confirmar_exclusao", True),
        key="w_confirmar_exclusao",
        on_change=lambda: st.session_state.update(confirmar_exclusao=st.session_state.w_confirmar_exclusao),
    )

    visiveis = _ordenar(_filtrar(metas, visao, hoje))
    if not visiveis:
        st.info("Nenhuma meta nesta visualização.")
    for meta in visiveis:
        _cartao(meta, tarefas_por_meta.get(meta["id"], []), hoje)
