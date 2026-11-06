from datetime import date

import streamlit as st

from database.metas import repo
from modules.metas.cartao import cartao, disparar_confete
from modules.metas.dados import menu_dados, mostrar_aviso
from modules.metas.dialogo import abrir_dialogo
from modules.metas.filtros import barra_busca
from modules.metas.regras import (
    VISOES,
    VISOES_NOME,
    filtrar_busca,
    filtrar_por_categorias,
    filtrar_visao,
    ordenar,
    resumo,
)


def painel_metricas(paineis):
    for coluna, (chave, titulo, icone, valor, texto) in zip(st.columns(len(paineis)), paineis, strict=True):
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

    mostrar_aviso()
    topo, acoes = st.columns([3, 2], vertical_alignment="center")
    topo.markdown(
        '<div class="atlas-title">Metas Pessoais</div>'
        '<div class="atlas-sub">Acompanhe o seu progresso e alcance os seus objetivos</div>',
        unsafe_allow_html=True,
    )
    with acoes, st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key="metas_topo_acoes"):
        menu_dados()
        if st.button("Nova meta", icon=":material/add:", type="primary", width="stretch"):
            abrir_dialogo()

    r = resumo(metas, hoje)
    painel_metricas([
        ("ativas", "Metas Semanais", "target", r["semana_feitas"],
         f"{r['semana_faltam']} ainda faltam nesta semana" if r["semana_faltam"] else "Nenhuma pendente nesta semana"),
        ("andamento", "Metas Mensais", "task_alt", f"{r['mes_feitas']}/{r['mes_total']}",
         f"{r['mes_total'] - r['mes_feitas']} pendentes neste mês"),
        ("atrasadas", "Metas Atrasadas", "error", r["atrasadas"],
         "Precisam de atenção" if r["atrasadas"] else "Nenhuma atrasada"),
    ])

    busca, selecionadas = barra_busca(categorias)

    # Busca e categorias valem para a visualização: as contagens do filtro já as consideram.
    base = filtrar_por_categorias(filtrar_busca(metas, busca), selecionadas)
    contagem = {v: len(filtrar_visao(base, v, hoje)) for v in VISOES}
    visao = st.segmented_control(
        "Visualização", VISOES, default="todas", key="visao_metas",
        format_func=lambda v: f"{VISOES_NOME[v]} ({contagem[v]})", label_visibility="collapsed",
    ) or "todas"

    # O estado é guardado à parte porque o widget perde o valor ao trocar de módulo.
    st.toggle(
        "Confirmar exclusões",
        value=st.session_state.get("confirmar_exclusao", True),
        key="w_confirmar_exclusao",
        on_change=lambda: st.session_state.update(confirmar_exclusao=st.session_state.w_confirmar_exclusao),
    )

    visiveis = ordenar(filtrar_visao(base, visao, hoje))
    if not visiveis:
        st.markdown(
            '<div style="text-align:center;color:#8d8d9c;padding:2rem 0">Nenhuma meta encontrada</div>',
            unsafe_allow_html=True,
        )
    for meta in visiveis:
        cartao(meta, tarefas_por_meta.get(meta["id"], []), hoje)
    disparar_confete()
