import re
from html import escape

import streamlit as st

from database.cores import cor_valida
from database.dinheiro import fmt_brl
from modules import ui

TIPO_ROTULO = {"entrada": "Entrada", "fixo": "Fixo", "variavel": "Variável"}
FORMA_ROTULO = {"pix": "Pix", "debito": "Débito", "credito": "Crédito", "dinheiro": "Dinheiro"}
FORMA_ICONE = {"pix": "qr_code_2", "debito": "account_balance", "credito": "credit_card", "dinheiro": "payments"}

COR_ENTRADA = "#4dd2a0"
COR_SAIDA = "#ff6b7a"
COR_DESTAQUE = "#d39bff"  # roxo claro: saldo e notas das legendas
COR_TIPO = {"fixo": "#b44cff", "variavel": "#4dd2c1"}  # rosca agrupada por tipo
_MARKDOWN_ESPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")


def md(conteudo, **kwargs):
    """HTML via st.markdown com o "$" trocado pela entidade: dois "R$" (ou um "$" digitado pelo usuário) no
    mesmo trecho virariam fórmula LaTeX."""
    st.markdown(conteudo.replace("$", "&#36;"), unsafe_allow_html=True, **kwargs)


def texto_markdown(texto):
    """Escapa texto do usuário onde o Streamlit interpreta Markdown: dica de botão, pílulas e st.error."""
    return _MARKDOWN_ESPECIAL.sub(r"\\\1", texto or "")


def icone(nome, classe=""):
    return f'<span class="material-icon {classe}">{nome}</span>'


def chip_categoria(nome, cor_categoria):
    c = cor_valida(cor_categoria)
    return f'<span class="fin-chip" style="--cat:{c}"><i></i>{escape(nome)}</span>'


def selo_banco(sigla, nome, cor_banco):
    c = cor_valida(cor_banco)
    return (f'<span class="fin-banco"><b style="--banco:{c}">{escape(sigla or "?")}</b>'
            f'<span>{escape(nome)}</span></span>')


def banco_html(lancamento):
    """Dinheiro leva o ícone dentro do mesmo selo dos bancos; lançamento sem banco mostra um traço."""
    if lancamento["forma"] == "dinheiro":
        return f'<span class="fin-banco dinheiro"><b>{icone("payments")}</b><span>Dinheiro</span></span>'
    if lancamento.get("banco_id") is None:
        return '<span class="fin-vazio">—</span>'
    return selo_banco(lancamento["banco_sigla"], lancamento["banco_nome"], lancamento["banco_cor"])


def forma_html(forma):
    return f'<span class="fin-forma">{icone(FORMA_ICONE[forma])}{FORMA_ROTULO[forma]}</span>'


def valor_html(lancamento):
    if lancamento["tipo"] == "entrada":
        return f'<span class="fin-valor entrada">{fmt_brl(lancamento["valor"], sinal=True)}</span>'
    return f'<span class="fin-valor saida">{fmt_brl(-lancamento["valor"])}</span>'


def descricao_html(lancamento):
    chip = chip_categoria(lancamento["categoria_nome"], lancamento["categoria_cor"])
    descricao = (lancamento.get("descricao") or "").strip()
    if not descricao:
        return f'<div class="fin-desc sem" title="{escape(lancamento["categoria_nome"], quote=True)}">{chip}</div>'
    return (f'<div class="fin-desc" title="{escape(descricao, quote=True)}">'
            f'<span class="fin-desc-txt">{escape(descricao)}</span>{chip}</div>')


def cabecalho_cartao(titulo, icone_nome=None, extra=""):
    ico = icone(icone_nome, "fin-card-ico") if icone_nome else ""
    md(f'<div class="fin-card-head"><span class="fin-card-titulo">{ico}{titulo}</span>'
       f'<span class="fin-card-extra">{extra}</span></div>')


def vazio(texto):
    md(f'<div class="fin-estado-vazio">{escape(texto)}</div>')


def escolha(rotulos, chave, atual, descricao):
    return ui.escolha(rotulos, chave, atual, descricao, required=True, width="stretch")


def avisar(texto):
    ui.agendar_aviso("fin_aviso", texto)


def mostrar_aviso():
    ui.mostrar_aviso("fin_aviso")
