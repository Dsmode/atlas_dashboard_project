from decimal import Decimal
from html import escape

import streamlit as st

from database.cores import COR_NEUTRA, cor_valida
from database.dinheiro import ZERO, fmt_brl
from database.financas import calculos as calc
from database.financas import repo
from modules.financas import comum, graficos

MESES_COLUNAS = 6  # Entradas × Saídas: o mês ativo e os 5 anteriores
MESES_FLUXO = 12  # Fluxo de caixa: os últimos 12 meses até o mês ativo
TOP = 5

_VISOES = ("Categoria", "Tipo")  # agrupamento da rosca; Tipo é fixos × variáveis
_VISAO_SALVA = "fin_dash_visao_salva"  # o estado do widget some ao trocar de módulo


def _classe_sinal(valor):
    return "positivo" if valor > 0 else ("negativo" if valor < 0 else "")


def _legenda(itens):
    return '<div class="chart-legend fin-dash-legenda">' + "".join(
        f'<span class="legenda-item"><i style="background:{cor_valida(c)}"></i>{rotulo} <b>{valor}</b></span>'
        for c, rotulo, valor in itens
    ) + "</div>"


def _vazio(cartao, texto):
    with st.container(key=f"fin_dash_vazio_{cartao}"):
        comum.vazio(texto)


def _item_resumo(classe, icone_nome, rotulo, valor, rodape=""):
    return (
        f'<div class="fin-resumo-item {classe}">{comum.icone(icone_nome, "fin-resumo-ico")}'
        f'<div class="fin-resumo-texto"><span class="fin-resumo-rotulo">{rotulo}</span>'
        f'<span class="fin-resumo-valor">{valor}</span>{rodape}</div></div>'
    )


def _resumo(resumo):
    pct = resumo["pct_gasto"]
    # Sem entrada no mês não há renda para comparar.
    if pct is None:
        valor_pct, barra, classe_pct = "—", '<span class="fin-resumo-barra vazia"><i></i></span>', "sem-renda"
    else:
        largura = min(float(pct), 100.0)
        classe_pct = "acima" if pct > 100 else ""
        valor_pct = calc.fmt_pct(pct)
        barra = f'<span class="fin-resumo-barra"><i style="width:{largura:.1f}%"></i></span>'
    saldo = resumo["saldo"]
    itens = (
        _item_resumo("entrada", "south_west", "Entradas", fmt_brl(resumo["entradas"]))
        + _item_resumo("saida", "north_east", "Saídas", fmt_brl(resumo["saidas"]))
        + _item_resumo(f"saldo {_classe_sinal(saldo)}", "account_balance_wallet", "Saldo do mês",
                       fmt_brl(saldo, sinal=True))
        + _item_resumo(f"pct {classe_pct}", "donut_small", "Da renda gasta", valor_pct, barra)
    )
    comum.md(f'<div class="fin-resumo">{itens}</div>')


def _cartao_entradas_saidas(totais, mes):
    linhas = calc.entradas_saidas(totais, calc.meses_ate(mes, MESES_COLUNAS))
    with st.container(key="fin_card_dash_es"):
        comum.cabecalho_cartao("Entradas × Saídas", "bar_chart", f"Últimos {MESES_COLUNAS} meses")
        entradas = sum((linha["entradas"] for linha in linhas), ZERO)
        saidas = sum((linha["saidas"] for linha in linhas), ZERO)
        if not entradas and not saidas:
            _vazio("es", f"Nenhum lançamento nos últimos {MESES_COLUNAS} meses.")
            return
        comum.md(_legenda([
            (comum.COR_ENTRADA, "Entradas", fmt_brl(entradas)),
            (comum.COR_SAIDA, "Saídas", fmt_brl(saidas)),
            (comum.COR_DESTAQUE, "Saldo", fmt_brl(entradas - saidas, sinal=True)),
        ]))
        st.altair_chart(graficos.entradas_saidas(linhas), width="stretch", theme=None)


def _guardar_visao():
    st.session_state[_VISAO_SALVA] = st.session_state.fin_dash_visao


def _legenda_rosca(grupos):
    linhas = "".join(
        f'<div class="fin-rosca-item{" zerado" if not g["valor"] else ""}" style="--cat:{cor_valida(g["cor"])}">'
        f'<i></i><span class="fin-rosca-nome">{escape(g["nome"])}</span>'
        f'<span class="fin-rosca-pct">{calc.fmt_pct(g["pct"])}</span><b>{fmt_brl(g["valor"])}</b></div>'
        for g in grupos
    )
    return f'<div class="fin-rosca-legenda">{linhas}</div>'


def _cartao_rosca(lancamentos, total_gastos):
    salva = st.session_state.setdefault(_VISAO_SALVA, _VISOES[0])
    with st.container(key="fin_card_dash_rosca"):
        with st.container(horizontal=True, vertical_alignment="center", key="fin_dash_rosca_topo"):
            comum.cabecalho_cartao("Para onde vai o dinheiro", "donut_large")
            escolha = st.segmented_control(
                "Agrupar por", _VISOES, default=salva, key="fin_dash_visao", required=True,
                on_change=_guardar_visao, label_visibility="collapsed",
            ) or salva
        if not total_gastos:
            _vazio("rosca", "Nenhum gasto neste mês.")
            return
        if escolha == "Categoria":
            grupos = calc.gastos_por_categoria(lancamentos)
        else:
            grupos = [dict(g, cor=comum.COR_TIPO[g["id"]]) for g in calc.gastos_por_tipo(lancamentos)]
        with st.container(horizontal=True, vertical_alignment="center", gap="medium", key="fin_dash_rosca_corpo"):
            st.altair_chart(graficos.rosca(grupos, total_gastos), width="content", theme=None)
            comum.md(_legenda_rosca(grupos), width="stretch")


def _cartao_fluxo(saldo_inicial, totais, mes):
    meses = calc.meses_ate(mes, MESES_FLUXO)
    with st.container(key="fin_card_dash_fluxo"):
        comum.cabecalho_cartao("Fluxo de caixa", "show_chart", f"Últimos {MESES_FLUXO} meses")
        if not totais and not saldo_inicial:
            _vazio("fluxo", "Sem lançamentos até este mês.")
            return
        linhas = calc.fluxo_caixa(saldo_inicial, totais, meses)
        atual = linhas[-1]["saldo"]
        itens = [
            (COR_NEUTRA, "Saldo inicial", fmt_brl(saldo_inicial)),
            (comum.COR_SAIDA if atual < 0 else comum.COR_DESTAQUE, f"Saldo em {calc.mes_curto(mes, com_ano=True)}",
             fmt_brl(atual)),
        ]
        if any(linha["saldo"] < 0 for linha in linhas):
            itens.append((comum.COR_SAIDA, "Mês no vermelho", ""))
        comum.md(_legenda(itens))
        st.altair_chart(graficos.fluxo_caixa(linhas), width="stretch", theme=None)


def _cartao_top(lancamentos, mes):
    with st.container(key="fin_card_dash_top"):
        comum.cabecalho_cartao(f"Top {TOP} maiores gastos por categoria", "leaderboard", calc.nome_mes(mes))
        todas = calc.gastos_por_categoria(lancamentos)
        if not todas:
            _vazio("top", "Nenhum gasto neste mês.")
            return
        top = todas[:TOP]
        qtd = len(todas)
        itens = [(comum.COR_DESTAQUE, f"{qtd} {'categoria' if qtd == 1 else 'categorias'} com gasto", "")]
        # Com até 5 categorias o ranking já mostra tudo; acima disso, mostra quanto o top concentra.
        if qtd > TOP:
            soma_pct = min(sum((g["pct"] for g in top), ZERO), Decimal(100))
            itens.append((comum.COR_DESTAQUE, f"As {TOP} maiores somam", calc.fmt_pct(soma_pct)))
        comum.md(_legenda(itens))
        st.altair_chart(graficos.top_categorias(top), width="stretch", theme=None)


def render(mes):
    fim = calc.fim_mes(mes)
    lancamentos = repo.listar_lancamentos(mes, fim)
    totais = repo.totais_por_mes(fim)
    saldo_inicial = repo.obter_saldo_inicial()
    resumo = calc.resumo_mes(lancamentos)

    with st.container(key="fin_dash"):
        _resumo(resumo)
        # A grade segue esta ordem: Entradas × Saídas, Para onde vai o dinheiro, Fluxo de caixa e Top 5.
        with st.container(key="fin_dash_grade"):
            _cartao_entradas_saidas(totais, mes)
            _cartao_rosca(lancamentos, resumo["saidas"])
            _cartao_fluxo(saldo_inicial, totais, mes)
            _cartao_top(lancamentos, mes)
