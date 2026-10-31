"""Filtros do Extrato: um botão para as três listas (categorias, bancos e formas), sem busca."""
import streamlit as st

from database import financas_calculos as calc
from modules.financas import comum


def estado(categorias, bancos):
    """Seleção guardada em session_state (sobrevive à troca de módulo); itens apagados saem do filtro."""
    filtros = st.session_state.setdefault("fin_filtros", {"categorias": set(), "bancos": set(), "formas": set()})
    filtros["categorias"].intersection_update(c["id"] for c in categorias)
    filtros["bancos"].intersection_update(b["id"] for b in bancos)
    return filtros


def _pilulas(rotulo, conjunto, opcoes, formatar, chave):
    """Pílulas de seleção múltipla ligadas a um conjunto. O estado do widget vem sempre do conjunto; o
    callback só o atualiza (duas pílulas podem dividir o mesmo conjunto, como as categorias)."""
    if not opcoes:
        return

    def mudou():
        conjunto.difference_update(opcoes)
        conjunto.update(st.session_state[chave] or [])

    st.session_state[chave] = [o for o in opcoes if o in conjunto]
    st.pills(rotulo, opcoes, selection_mode="multi", format_func=formatar, key=chave, on_change=mudou)


def barra(filtros, categorias, bancos):
    """Botão "Filtros" (popover) à direita, acima da grade. Devolve quantos filtros estão ativos."""
    ativos = sum(len(v) for v in filtros.values())
    cat_por_id = {c["id"]: c for c in categorias}
    banco_por_id = {b["id"]: b for b in bancos}

    def limpar():
        for conjunto in filtros.values():
            conjunto.clear()

    def nome_categoria(i):
        return comum.texto_markdown(cat_por_id[i]["nome"])

    with st.container(horizontal=True, horizontal_alignment="right", key="fin_ext_barra"):
        rotulo = f"Filtros · {ativos}" if ativos else "Filtros"
        with st.popover(rotulo, icon=":material/filter_list:", key="fin_ext_filtros"):
            for grupo, titulo in (("gasto", "Categorias de gasto"), ("entrada", "Categorias de entrada")):
                _pilulas(titulo, filtros["categorias"], [c["id"] for c in categorias if c["tipo"] == grupo],
                         nome_categoria, f"fin_flt_cat_{grupo}")
            _pilulas("Bancos", filtros["bancos"], list(banco_por_id),
                     lambda i: comum.texto_markdown(banco_por_id[i]["nome"]), "fin_flt_bancos")
            _pilulas("Forma de pagamento", filtros["formas"], list(calc.FORMAS), comum.FORMA_ROTULO.get,
                     "fin_flt_formas")
            st.button("Limpar", icon=":material/filter_list_off:", disabled=not ativos, width="stretch",
                      key="fin_flt_limpar", on_click=limpar)
    return ativos


def aplicar(lancamentos, filtros):
    """Cada grupo com seleção restringe; sem seleção, vale tudo. Filtro de banco esconde o dinheiro."""
    cats, bancos, formas = filtros["categorias"], filtros["bancos"], filtros["formas"]
    return [
        l for l in lancamentos
        if (not cats or l["categoria_id"] in cats)
        and (not bancos or l["banco_id"] in bancos)
        and (not formas or l["forma"] in formas)
    ]
