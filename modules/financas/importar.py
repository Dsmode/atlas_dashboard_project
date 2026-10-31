"""Aba Importar: só o visual por enquanto (selo "Em desenvolvimento", tudo desabilitado).

A ideia futura: anexar o extrato (OFX/CSV), escolher o banco e o período, e os lançamentos entram sozinhos.
"""
import streamlit as st

from database import financas_repo as repo
from modules.financas import comum

_AVISO = (
    '<div class="fin-imp-aviso">' + comum.icone("construction") +
    '<div><b>Em desenvolvimento</b><span>Em breve você poderá anexar o extrato do banco e os lançamentos '
    'entram sozinhos no Extrato. Por enquanto, esta tela é só uma prévia.</span></div></div>'
)

_SOLTAR = (
    '<div class="fin-imp-soltar">' + comum.icone("cloud_upload") +
    '<p>Arraste e solte seus arquivos de extrato aqui<br>ou clique para selecionar</p>'
    '<small>OFX ou CSV</small></div>'
)


def _bancos():
    bancos = repo.listar_bancos()
    if not bancos:
        return '<div class="fin-vazio">Nenhum banco ativo nas configurações.</div>'
    selos = "".join(
        f'<span class="fin-imp-banco">{comum.selo_banco(b["sigla"], b["nome"], b["cor"])}</span>'
        for b in bancos
    )
    return f'<div class="fin-imp-bancos">{selos}</div>'


def render(mes):
    comum.md(_AVISO)
    arquivos, opcoes = st.columns([3, 2], gap="medium")
    with arquivos, st.container(key="fin_card_imp_arquivos"):
        comum.md(_SOLTAR)
        comum.cabecalho_cartao("Arquivos selecionados", "description")
        comum.vazio("Nenhum arquivo selecionado.")
    with opcoes, st.container(key="fin_card_imp_opcoes"):
        comum.cabecalho_cartao("Selecione o banco", "account_balance")
        comum.md(_bancos())
        st.selectbox("Banco", ["Banco"], disabled=True, label_visibility="collapsed", key="fin_imp_banco")
        comum.cabecalho_cartao("Intervalo de datas", "date_range")
        inicio, fim = st.columns(2)
        inicio.date_input("Data início", value=None, disabled=True, format="DD/MM/YYYY", key="fin_imp_inicio")
        fim.date_input("Data fim", value=None, disabled=True, format="DD/MM/YYYY", key="fin_imp_fim")
        st.button("Importar dados", icon=":material/upload:", type="primary", disabled=True, width="stretch",
                  key="fin_imp_botao")
    with st.container(key="fin_card_imp_historico"):
        comum.cabecalho_cartao("Histórico de importação", "history")
        comum.md('<div class="fin-imp-tabela"><span>Data</span><span>Arquivo</span><span>Banco</span>'
                 '<span>Status</span></div>')
        comum.vazio("Nenhuma importação ainda.")
