"""Aba Extrato: formulário de lançamento e as listas de entradas, gastos fixos e gastos variáveis.

Grade 2×2: ↖ formulário, ↗ Entradas do mês, ↙ Gastos Fixos, ↘ Gastos Variáveis. Um único botão Filtros
(categorias, bancos e formas) vale para as três listas. Editar, excluir e copiar fixos abrem diálogos.

    formulario.py  campos do lançamento (formulário e edição) e o formulário ↖
    listas.py      os três blocos de lista e as ações de cada linha
    dialogos.py    editar, excluir e copiar os fixos do mês anterior
    filtros.py     botão Filtros e a filtragem
"""
import streamlit as st

from database import financas_calculos as calc
from database import financas_repo as repo
from modules.financas import comum
from modules.financas.extrato import filtros, formulario, listas


def render(mes):
    comum.mostrar_aviso()
    categorias = repo.listar_categorias()
    bancos = repo.listar_bancos(incluir_ocultos=True)  # lançamentos antigos ainda mostram banco oculto
    selecao = filtros.estado(categorias, bancos)
    filtrado = filtros.barra(selecao, categorias, bancos) > 0

    lancamentos = filtros.aplicar(repo.listar_lancamentos(mes, calc.fim_mes(mes)), selecao)
    por_tipo = {tipo: [l for l in lancamentos if l["tipo"] == tipo] for tipo in listas.BLOCOS}

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
