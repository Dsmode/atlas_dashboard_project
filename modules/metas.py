from datetime import date, timedelta

import streamlit as st

from components.checklist_sortable import checklist_sortable
from database import metas_repo as repo

PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}
PRIORIDADE_ORDEM = {"alta": 0, "media": 1, "baixa": 2}
STATUS = {"ativa": "Ativa", "concluida": "Concluída", "arquivada": "Arquivada"}
STATUS_ORDEM = {"ativa": 0, "concluida": 1, "arquivada": 2}

VISOES = ["todas", "semana", "mes", "atrasadas", "sem_prazo", "arquivadas"]
VISOES_NOME = {
    "semana": "Semanais", "mes": "Mensais", "atrasadas": "Atrasadas",
    "sem_prazo": "Sem prazo", "todas": "Todas", "arquivadas": "Arquivadas",
}

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
    """Metas arquivadas só aparecem na visão 'arquivadas'."""
    if visao == "arquivadas":
        return [m for m in metas if m["status"] == "arquivada"]
    metas = [m for m in metas if m["status"] != "arquivada"]
    if visao == "semana":
        ini, fim = _intervalo_semana(hoje)
        return [m for m in metas if m["prazo"] and ini <= m["prazo"] <= fim]
    if visao == "mes":
        ini, fim = _intervalo_mes(hoje)
        return [m for m in metas if m["prazo"] and ini <= m["prazo"] <= fim]
    if visao == "atrasadas":
        return [m for m in metas if _atrasada(m, hoje)]
    if visao == "sem_prazo":
        return [m for m in metas if m["prazo"] is None]
    return metas


def _ordenar(metas):
    """Prioridade (alta primeiro), depois status (ativas antes das concluídas), depois prazo."""
    return sorted(
        metas,
        key=lambda m: (
            PRIORIDADE_ORDEM[m["prioridade"]],
            STATUS_ORDEM[m["status"]],
            m["prazo"] or date.max,
        ),
    )


# ---------- diálogo de criação/edição ----------
# O diálogo trabalha numa cópia (session_state["dlg"]) e só grava no banco ao clicar em Salvar.
# Os diálogos do Streamlit reexecutam só a própria função a cada interação, por isso o estado
# inicial é montado em _abrir_dialogo, antes de chamar o diálogo.

def _abrir_dialogo(meta=None, tarefas=()):
    nonce = st.session_state.get("dlg_nonce", 0) + 1
    st.session_state.dlg_nonce = nonce
    st.session_state.dlg = {
        "nonce": nonce,
        "meta": meta,
        "proximo_uid": len(tarefas),
        "tarefas": [
            {"uid": i, "id": t["id"], "descricao": t["descricao"], "prazo": t["prazo"]}
            for i, t in enumerate(tarefas)
        ],
    }
    _dialogo_meta()


def _editor_tarefas(dlg):
    tarefas = dlg["tarefas"]
    st.markdown("**Tarefas**")
    if tarefas:
        for t in tarefas:
            c1, c2 = st.columns([12, 1], vertical_alignment="center")
            prazo = f"  ·  {_fmt_data(t['prazo'])}" if t["prazo"] else ""
            c1.markdown(f"{t['descricao']}<span style='color:#8d8d9c'>{prazo}</span>", unsafe_allow_html=True)
            if c2.button("", icon=":material/delete:", help="Excluir tarefa", key=f"dlg_del_{dlg['nonce']}_{t['uid']}"):
                dlg["tarefas"] = [x for x in tarefas if x["uid"] != t["uid"]]
                st.rerun(scope="fragment")
    else:
        st.caption("Nenhuma tarefa ainda.")

    with st.form(f"dlg_nova_tarefa_{dlg['nonce']}_{dlg['proximo_uid']}", border=False):
        c1, c2, c3 = st.columns([5, 3, 1], vertical_alignment="bottom")
        descricao = c1.text_input("Nova tarefa", placeholder="Nova tarefa...")
        prazo = c2.date_input("Prazo da tarefa (opcional)", value=None, format="DD/MM/YYYY")
        if c3.form_submit_button("", icon=":material/add:", help="Adicionar tarefa", use_container_width=True):
            if descricao.strip():
                dlg["tarefas"].append(
                    {"uid": dlg["proximo_uid"], "id": None, "descricao": descricao.strip(), "prazo": prazo}
                )
                dlg["proximo_uid"] += 1
                st.rerun(scope="fragment")


@st.dialog("Meta", width="large")
def _dialogo_meta():
    dlg = st.session_state.dlg
    meta = dlg["meta"]
    n = dlg["nonce"]

    titulo = st.text_input("Título", value=meta["titulo"] if meta else "", max_chars=150, key=f"dlg_titulo_{n}")
    descricao = st.text_area("Descrição", value=(meta["descricao"] or "") if meta else "", key=f"dlg_desc_{n}")
    col1, col2 = st.columns(2)
    prioridade = col1.selectbox(
        "Prioridade", list(PRIORIDADES),
        index=list(PRIORIDADES).index(meta["prioridade"]) if meta else 1,
        format_func=PRIORIDADES.get, key=f"dlg_prio_{n}",
    )
    prazo = col2.date_input(
        "Prazo (opcional)", value=meta["prazo"] if meta else None, format="DD/MM/YYYY", key=f"dlg_prazo_{n}",
    )

    _editor_tarefas(dlg)

    if st.button("Salvar", type="primary", use_container_width=True, key=f"dlg_salvar_{n}"):
        if not titulo.strip():
            st.error("O título é obrigatório.")
            return
        repo.salvar_meta(
            meta["id"] if meta else None, titulo.strip(), descricao.strip() or None,
            prioridade, prazo, dlg["tarefas"],
        )
        st.rerun()


@st.dialog("Confirmar exclusão")
def _dialogo_excluir(meta_id, nome):
    st.write(f"Excluir **{nome}**? Todas as tarefas dela também serão apagadas.")
    col1, col2 = st.columns(2)
    if col1.button("Cancelar", use_container_width=True):
        st.rerun()
    if col2.button("Excluir", type="primary", use_container_width=True):
        repo.excluir_meta(meta_id)
        st.rerun()


def _pedir_exclusao(meta_id, nome):
    if st.session_state.get("confirmar_exclusao", True):
        _dialogo_excluir(meta_id, nome)
    else:
        repo.excluir_meta(meta_id)
        st.rerun()


# ---------- cartão da meta ----------

def _checklist(meta_id, tarefas):
    """Checklist do cartão: marcar e reordenar. Cada evento do componente grava na hora."""
    itens = [
        {"id": t["id"], "descricao": t["descricao"], "prazo": _fmt_data(t["prazo"]) if t["prazo"] else "",
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
                _abrir_dialogo(meta, tarefas)
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
                _pedir_exclusao(meta["id"], meta["titulo"])

        if meta["descricao"]:
            st.markdown(f'<p class="meta-desc">{meta["descricao"]}</p>', unsafe_allow_html=True)

        st.progress(pct / 100, text=f"{feitas}/{total} tarefas · {pct}%" if total else "Sem tarefas ainda")

        # Estado de aberto/fechado em session_state: st.expander recolhe a cada rerun.
        abertos = st.session_state.setdefault("checklists_abertos", set())
        aberto = meta["id"] in abertos
        if total and st.button(
            f"Checklist ({feitas}/{total})", key=f"toggle_check_{meta['id']}",
            icon=":material/expand_less:" if aberto else ":material/expand_more:",
        ):
            abertos.symmetric_difference_update({meta["id"]})
            st.rerun()
        if total and aberto:
            _checklist(meta["id"], tarefas)


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
        _abrir_dialogo()

    contagem = {v: len(_filtrar(metas, v, hoje)) for v in VISOES}
    visao = st.segmented_control(
        "Visualização", VISOES, default="todas", key="visao_metas",
        format_func=lambda v: f"{VISOES_NOME[v]} ({contagem[v]})", label_visibility="collapsed",
    ) or "todas"

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
