"""Pedaços de interface usados por mais de uma aba do Controle Financeiro."""
import re
from html import escape

import streamlit as st

from database.financas_calculos import fmt_brl

TIPO_ROTULO = {"entrada": "Entrada", "fixo": "Fixo", "variavel": "Variável"}
FORMA_ROTULO = {"pix": "Pix", "debito": "Débito", "credito": "Crédito", "dinheiro": "Dinheiro"}
FORMA_ICONE = {"pix": "qr_code_2", "debito": "account_balance", "credito": "credit_card", "dinheiro": "payments"}

COR_PADRAO = "#b44cff"
COR_ENTRADA = "#4dd2a0"
COR_SAIDA = "#ff6b7a"
COR_DESTAQUE = "#d39bff"  # roxo claro: saldo e notas das legendas
COR_NEUTRA = "#8d8d9c"
COR_TIPO = {"fixo": "#b44cff", "variavel": "#4dd2c1"}  # rosca agrupada por tipo
_COR_VALIDA = re.compile(r"^#[0-9a-fA-F]{6}$")
_MARKDOWN_ESPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$])")


def md(conteudo, **kwargs):
    """HTML via st.markdown com o "$" trocado pela entidade: dois "R$" (ou um "$" digitado pelo usuário)
    no mesmo trecho virariam fórmula LaTeX."""
    st.markdown(conteudo.replace("$", "&#36;"), unsafe_allow_html=True, **kwargs)


def texto_markdown(texto):
    """Texto do usuário em lugares que o Streamlit interpreta como Markdown (dica de botão, pílulas, st.error)."""
    return _MARKDOWN_ESPECIAL.sub(r"\\\1", texto or "")


def escolha(rotulos, chave, atual, descricao):
    """Segmentado que nunca fica sem escolha: devolve a chave de `rotulos` ({chave: rótulo})."""
    escolhido = st.segmented_control(
        descricao, list(rotulos.values()), default=rotulos[atual], required=True, key=chave,
        label_visibility="collapsed", width="stretch",
    )
    return next((k for k, v in rotulos.items() if v == escolhido), atual)


def cor(valor):
    """Só `#rrggbb` entra em style=""; qualquer outra coisa vira o roxo padrão."""
    return valor if isinstance(valor, str) and _COR_VALIDA.match(valor) else COR_PADRAO


def icone(nome, classe=""):
    return f'<span class="material-icon {classe}">{nome}</span>'


def chip_categoria(nome, cor_categoria):
    """Ponto colorido + nome da categoria."""
    c = cor(cor_categoria)
    return f'<span class="fin-chip" style="--cat:{c}"><i></i>{escape(nome)}</span>'


def selo_banco(sigla, nome, cor_banco):
    """Sigla colorida no lugar da logo, com o nome ao lado."""
    c = cor(cor_banco)
    return (f'<span class="fin-banco"><b style="--banco:{c}">{escape(sigla or "?")}</b>'
            f'<span>{escape(nome)}</span></span>')


def banco_html(lancamento):
    """Banco do lançamento; dinheiro tem ícone próprio e lançamento sem banco mostra um traço."""
    if lancamento["forma"] == "dinheiro":
        return f'<span class="fin-banco dinheiro">{icone("payments")}<span>Dinheiro</span></span>'
    if lancamento.get("banco_id") is None:
        return '<span class="fin-vazio">—</span>'
    return selo_banco(lancamento["banco_sigla"], lancamento["banco_nome"], lancamento["banco_cor"])


def forma_html(forma):
    return f'<span class="fin-forma">{icone(FORMA_ICONE[forma])}{FORMA_ROTULO[forma]}</span>'


def valor_html(lancamento):
    """Entrada em verde com '+', gasto em vermelho com '-'."""
    if lancamento["tipo"] == "entrada":
        return f'<span class="fin-valor entrada">{fmt_brl(lancamento["valor"], sinal=True)}</span>'
    return f'<span class="fin-valor saida">{fmt_brl(-lancamento["valor"])}</span>'


def descricao_html(lancamento):
    """Descrição com a categoria embaixo; sem descrição, a própria categoria vira o texto principal."""
    chip = chip_categoria(lancamento["categoria_nome"], lancamento["categoria_cor"])
    descricao = (lancamento.get("descricao") or "").strip()
    if not descricao:
        return f'<div class="fin-desc sem" title="{escape(lancamento["categoria_nome"], quote=True)}">{chip}</div>'
    return (f'<div class="fin-desc" title="{escape(descricao, quote=True)}">'
            f'<span class="fin-desc-txt">{escape(descricao)}</span>{chip}</div>')


def secao(icone_nome, titulo):
    """Título de seção de diálogo (mesmo visual dos diálogos das Metas)."""
    md(f'<div class="dlg-sec">{icone(icone_nome)}{titulo}</div>')


def cabecalho_cartao(titulo, icone_nome=None, extra=""):
    """Linha de título dos cartões (blocos do Extrato e gráficos do Dashboard); `extra` vai à direita."""
    ico = icone(icone_nome, "fin-card-ico") if icone_nome else ""
    md(f'<div class="fin-card-head"><span class="fin-card-titulo">{ico}{titulo}</span>'
       f'<span class="fin-card-extra">{extra}</span></div>')


def vazio(texto):
    md(f'<div class="fin-estado-vazio">{escape(texto)}</div>')


def avisar(texto):
    """Toast mostrado no começo da próxima execução (o st.rerun que atualiza a tela apagaria um toast imediato)."""
    st.session_state.fin_aviso = texto


def mostrar_aviso():
    texto = st.session_state.pop("fin_aviso", None)
    if texto:
        st.toast(texto, icon=":material/check_circle:")
