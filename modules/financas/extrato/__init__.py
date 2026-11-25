"""Aba Extrato: formulário de lançamento e as listas de entradas, gastos fixos e gastos variáveis.

A grade é 2×2 (formulário, Entradas, Fixos, Variáveis) e um único botão Filtros vale para as três listas e
para a faixa de previsão do mês.
Editar, excluir e copiar fixos abrem diálogos.

formulario.py  campos do lançamento (formulário e edição) e o formulário de novo lançamento
listas.py      os três blocos de lista e as ações de cada linha
dialogos.py    editar, excluir e copiar os fixos do mês anterior
filtros.py     botão Filtros e a filtragem"""

import streamlit as st

from database.dinheiro import fmt_brl
from database.financas import calculos as calc
from database.financas import repo
from modules.financas import comum
from modules.financas.extrato import filtros, formulario, listas


def _faixa_previsao(lancamentos, filtrado):
    previsao = calc.previsao_mes(lancamentos)
    saldo = previsao["saldo"]
    classe = "positivo" if saldo > 0 else ("negativo" if saldo < 0 else "")
    selo = '<span class="fin-selo">filtrado</span>' if filtrado else ""
    comum.md(
        f'<div class="fin-ext-previsao"><span class="titulo">{comum.icone("query_stats")}Previsão do mês</span>'
        f'<span>Entradas previstas <b>{fmt_brl(previsao["entradas"])}</b></span>'
        f'<span>Gastos previstos <b>{fmt_brl(previsao["gastos"])}</b></span>'
        f'<span class="saldo {classe}">Saldo previsto <b>{fmt_brl(saldo, sinal=True)}</b></span>{selo}</div>'
    )


def render(mes):
    comum.mostrar_aviso()
    categorias = repo.listar_categorias()
    bancos = repo.listar_bancos(incluir_ocultos=True)  # lançamentos antigos ainda mostram banco oculto
    selecao = filtros.estado(categorias, bancos)
    filtrado = filtros.barra(selecao, categorias, bancos) > 0

    lancamentos = filtros.aplicar(repo.listar_lancamentos(mes, calc.fim_mes(mes)), selecao)
    por_tipo = {tipo: [lanc for lanc in lancamentos if lanc["tipo"] == tipo] for tipo in listas.BLOCOS}

    _faixa_previsao(lancamentos, filtrado)

    with st.container(key="fin_ext_grade"):
        esquerda, direita = st.columns(2, gap="medium")
        with esquerda, st.container(key="fin_card_ext_form"):
            formulario.formulario(mes)
        with direita:
            listas.bloco("entrada", por_tipo["entrada"], mes, filtrado)
        esquerda, direita = st.columns(2, gap="medium")
        with esquerda:
            listas.bloco("fixo", por_tipo["fixo"], mes, filtrado)
        with direita:
            listas.bloco("variavel", por_tipo["variavel"], mes, filtrado)
