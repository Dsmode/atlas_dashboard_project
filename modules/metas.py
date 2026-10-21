import unicodedata
from datetime import date, timedelta
from html import escape

import streamlit as st

from components.checklist_sortable import checklist_sortable
from database import metas_repo as repo

PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}
PRIORIDADE_ORDEM = {"alta": 0, "media": 1, "baixa": 2}
STATUS = {"ativa": "Ativa", "atrasada": "Atrasada", "concluida": "Concluída", "arquivada": "Arquivada"}
STATUS_ORDEM = {"ativa": 0, "concluida": 1, "arquivada": 2}

VISOES = ["todas", "semana", "mes", "atrasadas", "sem_prazo", "arquivadas"]
VISOES_NOME = {
    "semana": "Semanais", "mes": "Mensais", "atrasadas": "Atrasadas",
    "sem_prazo": "Sem prazo", "todas": "Todas", "arquivadas": "Arquivadas",
}

COR_PADRAO_CATEGORIA = "#b44cff"
NOME_CATEGORIA_MAX = 30


def _cor_texto(cor):
    """Texto escuro ou claro, conforme a luminosidade da cor de fundo escolhida."""
    r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
    return "#14141a" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"


def _chip(categoria):
    return (
        f'<span class="cat-chip" style="background:{categoria["cor"]};color:{_cor_texto(categoria["cor"])}">'
        f'{escape(categoria["nome"])}</span>'
    )


def _chips(categorias):
    return f'<div class="cat-chips">{"".join(_chip(c) for c in categorias)}</div>' if categorias else ""


def _normalizar(texto):
    """Minúsculas e sem acentos, para a busca ignorar caixa e acentuação."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def _filtrar_busca(metas, texto):
    """Metas cujo título ou descrição contém o texto digitado; vazio devolve todas."""
    termo = _normalizar(texto.strip())
    if not termo:
        return list(metas)
    return [m for m in metas if termo in _normalizar(m["titulo"]) or termo in _normalizar(m["descricao"])]


def _filtrar_por_categorias(metas, categoria_ids):
    """Metas que têm ao menos uma das categorias; sem seleção, devolve todas."""
    ids = set(categoria_ids)
    if not ids:
        return list(metas)
    return [m for m in metas if ids & {c["id"] for c in m["categorias"]}]


def _bolinhas(categorias):
    return "".join(f'<span class="cat-dot" style="background:{c["cor"]}"></span>' for c in categorias)


def _campo_busca():
    """Busca por título e descrição. O texto fica em session_state para sobreviver à troca de módulo."""
    def guardar():
        st.session_state.busca_metas = st.session_state.w_busca_metas

    if "w_busca_metas" not in st.session_state:
        st.session_state.w_busca_metas = st.session_state.get("busca_metas", "")
    return st.text_input(
        "Buscar metas", key="w_busca_metas", on_change=guardar, placeholder="Buscar metas por título ou descrição",
        label_visibility="collapsed",
    )


def _filtro_categorias(categorias):
    """Botão de filtro por categorias (popover). Sem categoria marcada vale 'Geral' (todas as metas).

    A seleção fica em session_state para sobreviver à troca de módulo. Devolve os ids marcados
    que ainda existem no catálogo.
    """
    selecionadas = st.session_state.setdefault("filtro_categorias", set())
    ativas = selecionadas & {c["id"] for c in categorias}

    def limpar():
        selecionadas.clear()
        for c in categorias:
            st.session_state[f"flt_cat_{c['id']}"] = False

    def marcar(categoria_id):
        (selecionadas.add if st.session_state[f"flt_cat_{categoria_id}"] else selecionadas.discard)(categoria_id)

    with st.popover("Categorias", icon=":material/label:"):
        st.button(
            "Geral", type="secondary" if ativas else "primary", use_container_width=True,
            key="flt_geral", on_click=limpar,
        )
        for c in categorias:
            chave = f"flt_cat_{c['id']}"
            if chave not in st.session_state:
                st.session_state[chave] = c["id"] in ativas
            p0, c1 = st.columns([1, 8], vertical_alignment="center")
            p0.markdown(f'<span class="cat-dot" style="background:{c["cor"]}"></span>', unsafe_allow_html=True)
            c1.checkbox(c["nome"], key=chave, on_change=marcar, args=(c["id"],))
        st.button("Limpar", disabled=not ativas, use_container_width=True, key="flt_limpar", on_click=limpar)

    marcadas = [c for c in categorias if c["id"] in ativas]
    if marcadas:
        st.markdown(_bolinhas(marcadas), unsafe_allow_html=True)
    return ativas


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


def _categoria(meta, hoje):
    """Categoria exibida no cartão: ativa, atrasada, concluída ou arquivada."""
    return "atrasada" if _atrasada(meta, hoje) else meta["status"]


def _resumo(metas, hoje):
    """Números dos três painéis (metas arquivadas ficam de fora)."""
    semana = _filtrar(metas, "semana", hoje)
    mes = _filtrar(metas, "mes", hoje)
    feitas = lambda lista: sum(1 for m in lista if m["status"] == "concluida")
    return {
        "semana_feitas": feitas(semana),
        "semana_faltam": len(semana) - feitas(semana),
        "mes_feitas": feitas(mes),
        "mes_total": len(mes),
        "atrasadas": len(_filtrar(metas, "atrasadas", hoje)),
    }


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
        "categorias": {c["id"] for c in meta["categorias"]} if meta else set(),
        "cat_modo": None,  # None | "nova" | ("editar", id) | ("excluir", id)
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


def _form_categoria(dlg, categoria=None):
    """Formulário de criar/editar categoria: só nome e cor. O catálogo grava na hora."""
    n = dlg["nonce"]
    sufixo = f"{n}_{categoria['id'] if categoria else 'nova'}"
    nome = st.text_input(
        "Nome da categoria", value=categoria["nome"] if categoria else "", max_chars=NOME_CATEGORIA_MAX,
        key=f"cat_nome_{sufixo}",
    )
    cor = st.color_picker(
        "Cor", value=categoria["cor"] if categoria else COR_PADRAO_CATEGORIA, key=f"cat_cor_{sufixo}",
    )
    b1, b2 = st.columns(2)
    if b1.button("Cancelar", use_container_width=True, key=f"cat_cancel_{sufixo}"):
        dlg["cat_modo"] = None
        st.rerun(scope="fragment")
    if b2.button("Salvar", type="primary", use_container_width=True, key=f"cat_save_{sufixo}"):
        if not nome.strip():
            st.error("Dê um nome à categoria.")
            return
        try:
            if categoria:
                repo.atualizar_categoria(categoria["id"], nome.strip(), cor)
            else:
                dlg["categorias"].add(repo.criar_categoria(nome.strip(), cor))
        except repo.CategoriaDuplicada:
            st.error("Já existe uma categoria com esse nome.")
            return
        dlg["cat_modo"] = None
        st.rerun(scope="fragment")


def _seletor_categorias(dlg):
    """Botão 'Categorias' (popover estilo Trello): marcar, criar, editar e excluir categorias."""
    n = dlg["nonce"]
    categorias = repo.listar_categorias()
    selecionadas = dlg["categorias"]
    modo = dlg["cat_modo"]
    por_id = {c["id"]: c for c in categorias}

    with st.popover("Categorias", icon=":material/label:"):
        if modo == "nova":
            _form_categoria(dlg)
        elif isinstance(modo, tuple) and modo[1] in por_id:
            if modo[0] == "editar":
                _form_categoria(dlg, por_id[modo[1]])
            else:
                c = por_id[modo[1]]
                st.write(
                    f"Excluir **{c['nome']}**? Ela será removida de {c['em_uso']} meta(s); as metas permanecem."
                )
                b1, b2 = st.columns(2)
                if b1.button("Cancelar", use_container_width=True, key=f"cat_xno_{n}"):
                    dlg["cat_modo"] = None
                    st.rerun(scope="fragment")
                if b2.button("Excluir", type="primary", use_container_width=True, key=f"cat_xsim_{n}"):
                    repo.excluir_categoria(c["id"])
                    selecionadas.discard(c["id"])
                    dlg["cat_modo"] = None
                    st.rerun(scope="fragment")
        else:
            if not categorias:
                st.caption("Nenhuma categoria ainda.")
            for c in categorias:
                p0, c1, c2, c3 = st.columns([1, 8, 1, 1], vertical_alignment="center")
                p0.markdown(f'<span class="cat-dot" style="background:{c["cor"]}"></span>', unsafe_allow_html=True)
                marcada = c1.checkbox(
                    c["nome"], value=c["id"] in selecionadas, key=f"cat_chk_{n}_{c['id']}",
                )
                (selecionadas.add if marcada else selecionadas.discard)(c["id"])
                if c2.button("", icon=":material/edit:", help="Editar categoria", key=f"cat_ed_{n}_{c['id']}"):
                    dlg["cat_modo"] = ("editar", c["id"])
                    st.rerun(scope="fragment")
                if c3.button("", icon=":material/delete:", help="Excluir categoria", key=f"cat_ex_{n}_{c['id']}"):
                    dlg["cat_modo"] = ("excluir", c["id"])
                    st.rerun(scope="fragment")
            if st.button("Criar nova categoria", icon=":material/add:", use_container_width=True, key=f"cat_new_{n}"):
                dlg["cat_modo"] = "nova"
                st.rerun(scope="fragment")

    marcadas = [c for c in categorias if c["id"] in selecionadas]
    if marcadas:
        st.markdown(_chips(marcadas), unsafe_allow_html=True)


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

    _seletor_categorias(dlg)

    _editor_tarefas(dlg)

    if st.button("Salvar", type="primary", use_container_width=True, key=f"dlg_salvar_{n}"):
        if not titulo.strip():
            st.error("O título é obrigatório.")
            return
        repo.salvar_meta(
            meta["id"] if meta else None, titulo.strip(), descricao.strip() or None,
            prioridade, prazo, dlg["tarefas"], sorted(dlg["categorias"]),
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

    categoria = _categoria(meta, hoje)

    with st.container(border=True, key=f"meta_card_{meta['id']}"):
        topo, acoes = st.columns([5, 3], vertical_alignment="top")
        with topo:
            st.markdown(
                f'<p class="meta-title">{meta["titulo"]}'
                f'<span class="badge status-{categoria}">{STATUS[categoria]}</span>'
                f'<span class="badge {meta["prioridade"]}">{PRIORIDADES[meta["prioridade"]]}</span></p>',
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

        if meta["categorias"]:
            st.markdown(_chips(meta["categorias"]), unsafe_allow_html=True)

        if meta["descricao"]:
            st.markdown(f'<p class="meta-desc">{meta["descricao"]}</p>', unsafe_allow_html=True)

        st.markdown(
            f'<div class="meta-info">'
            f'<span class="material-icon">calendar_today</span>Prazo: {_fmt_data(meta["prazo"])}'
            f'<span class="material-icon">task_alt</span>{feitas} / {total} tarefas</div>'
            f'<div class="prog-head"><span>Tarefas</span><b>{feitas} / {total}</b></div>'
            f'<div class="prog-track"><div class="prog-fill" style="width:{pct}%"></div></div>'
            f'<div class="prog-foot">{pct}% concluído</div>',
            unsafe_allow_html=True,
        )

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

def _painel_metricas(paineis):
    for coluna, (chave, titulo, icone, valor, texto) in zip(st.columns(len(paineis)), paineis):
        with coluna, st.container(border=True, key=f"meta_panel_{chave}"):
            st.markdown(
                f'<div class="panel-head"><span>{titulo}</span><span class="material-icon">{icone}</span></div>'
                f'<div class="panel-value">{valor}</div><div class="panel-sub">{texto}</div>',
                unsafe_allow_html=True,
            )


def render():
    hoje = date.today()
    metas = repo.listar_metas()
    categorias = repo.listar_categorias()
    tarefas_por_meta = {}
    for t in repo.listar_tarefas():
        tarefas_por_meta.setdefault(t["meta_id"], []).append(t)

    topo, botao = st.columns([3, 2], vertical_alignment="center")
    topo.markdown(
        '<div class="atlas-title">Metas Pessoais</div>'
        '<div class="atlas-sub">Acompanhe o seu progresso e alcance os seus objetivos</div>',
        unsafe_allow_html=True,
    )
    if botao.button("Nova meta", icon=":material/add:", type="primary", use_container_width=True):
        _abrir_dialogo()

    r = _resumo(metas, hoje)
    _painel_metricas([
        ("ativas", "Metas Semanais", "target", r["semana_feitas"],
         f"{r['semana_faltam']} ainda faltam nesta semana" if r["semana_faltam"] else "Nenhuma pendente nesta semana"),
        ("andamento", "Metas Mensais", "task_alt", f"{r['mes_feitas']}/{r['mes_total']}",
         f"{r['mes_total'] - r['mes_feitas']} pendentes neste mês"),
        ("atrasadas", "Metas Atrasadas", "error", r["atrasadas"],
         "Precisam de atenção" if r["atrasadas"] else "Nenhuma atrasada"),
    ])

    busca_col, cat_col = st.columns([4, 2], vertical_alignment="center")
    with busca_col:
        busca = _campo_busca()
    with cat_col:
        selecionadas = _filtro_categorias(categorias)

    # Busca e categorias valem para a visualização: as contagens do filtro já as consideram.
    base = _filtrar_por_categorias(_filtrar_busca(metas, busca), selecionadas)
    contagem = {v: len(_filtrar(base, v, hoje)) for v in VISOES}
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

    visiveis = _ordenar(_filtrar(base, visao, hoje))
    if not visiveis:
        st.markdown(
            '<div style="text-align:center;color:#8d8d9c;padding:2rem 0">Nenhuma meta encontrada</div>',
            unsafe_allow_html=True,
        )
    for meta in visiveis:
        _cartao(meta, tarefas_por_meta.get(meta["id"], []), hoje)
