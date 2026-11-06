import streamlit as st

from database.cores import cor_valida
from modules.metas.visual import COR_GERAL, cor_texto


def _ponto_cor(cor):
    st.markdown(f'<span class="cat-dot" style="background:{cor}"></span>', unsafe_allow_html=True)


def _popover_categorias(categorias, selecionadas, ativas):
    """Filtro por categorias num popover. "Geral" é a categoria do sistema: fica ativa enquanto nenhuma outra
    estiver marcada, marcar uma categoria a desliga e marcar "Geral" desmarca as outras."""
    def limpar():
        selecionadas.clear()

    def clicar_geral():
        if st.session_state.flt_geral:
            selecionadas.clear()

    def marcar(categoria_id):
        (selecionadas.add if st.session_state[f"flt_cat_{categoria_id}"] else selecionadas.discard)(categoria_id)

    rotulo = f"Categorias · {len(ativas)}" if ativas else "Categorias"
    with st.popover(rotulo, icon=":material/label:", key="busca_categorias"):
        # Os checkboxes sempre partem da seleção guardada; os callbacks só a atualizam.
        st.session_state.flt_geral = not ativas
        col_ponto, col_nome = st.columns([1, 8], vertical_alignment="center")
        with col_ponto:
            _ponto_cor(COR_GERAL)
        col_nome.checkbox("Geral", key="flt_geral", on_change=clicar_geral)
        for c in categorias:
            chave = f"flt_cat_{c['id']}"
            st.session_state[chave] = c["id"] in ativas
            col_ponto, col_nome = st.columns([1, 8], vertical_alignment="center")
            with col_ponto:
                _ponto_cor(cor_valida(c["cor"]))
            col_nome.checkbox(c["nome"], key=chave, on_change=marcar, args=(c["id"],))
        st.button("Limpar", disabled=not ativas, width="stretch", key="flt_limpar", on_click=limpar)


def _chips_filtro(marcadas, selecionadas):
    # A cor de cada chip vem do CSS, por chave: o botão do Streamlit não aceita estilo próprio.
    """Categorias marcadas no filtro, em chips coloridos com x. A linha tem altura fixa (CSS) e existe mesmo sem
    seleção, para a página não se deslocar ao marcar."""
    st.html("<style>" + "".join(
        f'.st-key-flt_chip_{c["id"]} button{{background:{cor_valida(c["cor"])};color:{cor_texto(c["cor"])}}}' for c in marcadas
    ) + "</style>")
    with st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key="flt_chips"):
        if not marcadas:
            st.html('<span class="flt-vazio">Todas as categorias</span>')
            return
        for c in marcadas:
            st.button(
                c["nome"], icon=":material/close:", key=f"flt_chip_{c['id']}", help="Remover do filtro",
                on_click=selecionadas.discard, args=(c["id"],),
            )
        st.button("Limpar tudo", type="tertiary", key="flt_limpar_tudo", on_click=selecionadas.clear)


def barra_busca(categorias):
    """Pílula única de busca e filtro: lupa, campo, X para limpar (só com texto) e o botão de categorias. Devolve
    (texto, ids das categorias marcadas). O texto e a seleção ficam em session_state para sobreviver à troca
    de módulo, e a seleção só mantém categorias que ainda existem."""
    def guardar():
        st.session_state.busca_metas = st.session_state.w_busca_metas

    def limpar():
        st.session_state.busca_metas = ""
        st.session_state.w_busca_metas = ""

    if "w_busca_metas" not in st.session_state:
        st.session_state.w_busca_metas = st.session_state.get("busca_metas", "")
    selecionadas = st.session_state.setdefault("filtro_categorias", set())
    # Categoria excluída sai do filtro.
    selecionadas.intersection_update(c["id"] for c in categorias)
    ativas = set(selecionadas)

    with st.container(horizontal=True, vertical_alignment="center", gap=None, key="busca_barra"):
        st.markdown('<span class="material-icon busca-lupa">search</span>', unsafe_allow_html=True)
        texto = st.text_input(
            "Buscar metas", key="w_busca_metas", on_change=guardar, placeholder="Buscar metas por título ou descrição",
            label_visibility="collapsed", width="stretch",
        )
        if texto:
            st.button("", icon=":material/close:", type="tertiary", help="Limpar busca", key="busca_limpar", on_click=limpar)
        _popover_categorias(categorias, selecionadas, ativas)

    _chips_filtro([c for c in categorias if c["id"] in ativas], selecionadas)
    return texto, ativas
