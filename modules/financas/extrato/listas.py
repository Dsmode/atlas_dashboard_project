from html import escape

import streamlit as st

from database.dinheiro import ZERO, fmt_brl
from modules.financas import comum
from modules.financas.extrato import dialogos

# Altura da área rolável de cada lista, para o cartão ficar com a altura do formulário.
LISTA_ALTURA = 372

# chave: (título, ícone, texto do estado vazio)
BLOCOS = {
    "entrada": ("Entradas do mês", "trending_up", "Nenhuma entrada neste mês."),
    "fixo": ("Gastos Fixos", "event_repeat", "Nenhum gasto fixo neste mês."),
    "variavel": ("Gastos Variáveis", "shopping_bag", "Nenhum gasto variável neste mês."),
}

_CABECALHO = (
    '<div class="fin-ext-cab"><span>Data</span><span>Descrição</span><span class="dir">Valor</span>'
    '<span class="fin-ext-cab-forma">Forma</span><span>Banco</span><span class="dir">Ações</span></div>'
)


def _banco_titulo(lanc):
    if lanc["forma"] == "dinheiro":
        return "Dinheiro"
    return lanc["banco_nome"] if lanc.get("banco_id") is not None else "Sem banco"


def _linha(lanc):
    i = lanc["id"]
    with st.container(horizontal=True, vertical_alignment="center", gap=None, key=f"fin_ext_lin_{i}"):
        comum.md(
            f'<div class="fin-ext-grade"><span class="fin-ext-data">{lanc["data"]:%d/%m}</span>'
            f'{comum.descricao_html(lanc)}'
            f'<span class="fin-ext-valor">{comum.valor_html(lanc)}</span>'
            f'<span class="fin-ext-forma" title="{comum.FORMA_ROTULO[lanc["forma"]]}">{comum.forma_html(lanc["forma"])}</span>'
            f'<span class="fin-ext-banco" title="{escape(_banco_titulo(lanc), quote=True)}">{comum.banco_html(lanc)}</span>'
            '</div>',
            width="stretch",
        )
        with st.container(horizontal=True, gap="xsmall", width="content", key=f"fin_ext_acoes_{i}"):
            # A dica do botão é Markdown, sem HTML: o texto do usuário vai com os símbolos escapados.
            observacao = (lanc.get("observacao") or "").strip()
            st.button("", icon=":material/sticky_note_2:", key=f"fin_ext_bobs_{i}", disabled=not observacao,
                      help=comum.texto_markdown(observacao) if observacao else "Sem observação")
            if st.button("", icon=":material/edit:", key=f"fin_ext_bed_{i}", help="Editar"):
                dialogos.abrir_edicao(lanc)
            if st.button("", icon=":material/delete:", key=f"fin_ext_bdel_{i}", help="Excluir"):
                dialogos.dialogo_exclusao(lanc)


def bloco(tipo, lancamentos, mes, filtrado):
    titulo, icone_nome, texto_vazio = BLOCOS[tipo]
    total = sum((lanc["valor"] for lanc in lancamentos), ZERO)
    with st.container(key=f"fin_card_ext_{tipo}"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", key=f"fin_ext_topo_{tipo}"):
            classe = "entrada" if tipo == "entrada" else "saida"
            comum.cabecalho_cartao(
                f'{titulo}<span class="fin-ext-total {classe}">· {fmt_brl(total)}</span>',
                icone_nome,
                '<span class="fin-selo">filtrado</span>' if filtrado else "",
            )
            if tipo == "fixo" and st.button("Copiar do mês anterior", icon=":material/content_copy:",
                                            key="fin_ext_copiar", help="Trazer os gastos fixos do mês anterior"):
                dialogos.abrir_copia(mes)
        with st.container(height=LISTA_ALTURA, border=False, key=f"fin_ext_lista_{tipo}"):
            if not lancamentos:
                comum.vazio("Nada com os filtros escolhidos." if filtrado else texto_vazio)
                return
            comum.md(_CABECALHO)
            for lanc in lancamentos:
                _linha(lanc)
