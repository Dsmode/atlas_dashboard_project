"""Histórico de importação (mais recentes primeiro) e o diálogo de desfazer.

Os diálogos do Streamlit reexecutam só a própria função: o estado vai em `st.session_state["fin_hist_desf"]`,
montado em `abrir_desfazer` antes de abrir.
"""
from html import escape

import streamlit as st

from database import financas_repo as repo
from modules.financas import comum

LIMITE = 50
_STATUS = {"concluida": ("Concluída", "ok"), "desfeita": ("Desfeita", "off")}
_CABECALHO = ("Data/hora", "Arquivo", "Banco", "Observação", "Período", "Importados", "Status")


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _vazio():
    return '<span class="fin-vazio">—</span>'


def _celula_texto(texto, classe):
    if not texto:
        return f'<span class="{classe}">{_vazio()}</span>'
    return f'<span class="{classe}" title="{escape(texto, quote=True)}">{escape(texto)}</span>'


def _linha_html(i):
    rotulo, classe = _STATUS[i["status"]]
    banco = comum.selo_banco(i["banco_sigla"], i["banco_nome"], i["banco_cor"]) if i["banco_nome"] else _vazio()
    detalhes = []
    if i["qtd_duplicadas"]:
        detalhes.append(_plural(i["qtd_duplicadas"], "já existia", "já existiam"))
    if i["qtd_ignoradas"]:
        detalhes.append(_plural(i["qtd_ignoradas"], "ignorado", "ignorados"))
    detalhe = f"<small>{' · '.join(detalhes)}</small>" if detalhes else ""
    periodo = f'{i["periodo_inicio"]:%d/%m/%Y} a {i["periodo_fim"]:%d/%m/%Y}'
    return (
        f'<div class="fin-hist-linha{" desfeita" if i["status"] == "desfeita" else ""}">'
        f'<span>{i["data_hora"]:%d/%m/%Y %H:%M}</span>{_celula_texto(i["arquivo"], "arq")}<span>{banco}</span>'
        f'{_celula_texto(i["observacao"], "obs")}<span>{periodo}</span>'
        f'<span class="qtd"><b>{i["qtd_importadas"]}</b>{detalhe}</span>'
        f'<span><i class="fin-hist-status {classe}">{rotulo}</i></span></div>'
    )


def render_historico():
    importacoes = repo.listar_importacoes(LIMITE)
    with st.container(key="fin_card_imp_historico"):
        comum.cabecalho_cartao("Histórico de importação", "history")
        cabecalho = "".join(f"<span>{rotulo}</span>" for rotulo in _CABECALHO)
        comum.md(f'<div class="fin-hist-linha fin-hist-cab">{cabecalho}</div>')
        if not importacoes:
            comum.vazio("Nenhuma importação ainda.")
            return
        with st.container(key="fin_hist_lista"):
            for i in importacoes:
                with st.container(horizontal=True, vertical_alignment="center", gap="small",
                                  key=f"fin_hist_lin_{i['id']}"):
                    comum.md(_linha_html(i), width="stretch")
                    if i["status"] == "concluida":
                        if st.button("Desfazer", icon=":material/undo:", key=f"fin_hist_desf_{i['id']}",
                                     help="Apaga do Extrato os lançamentos desta importação"):
                            abrir_desfazer(i)
                    else:
                        comum.md('<div class="fin-hist-reserva"></div>')


# ---------- desfazer ----------

def abrir_desfazer(importacao):
    st.session_state.fin_hist_desf = {"id": importacao["id"], "arquivo": importacao["arquivo"]}
    _dialogo_desfazer()


@st.dialog("Desfazer importação", width="medium")
def _dialogo_desfazer():
    estado = st.session_state["fin_hist_desf"]
    n = repo.contar_lancamentos_importacao(estado["id"])
    arquivo = escape(estado["arquivo"])
    if n == 0:
        comum.md(f"<p>Nenhum lançamento desta importação existe mais no Extrato (<b>{arquivo}</b>). "
                 "Só o registro será marcado como desfeito.</p>")
    else:
        comum.md(f"<p>Apagar {_plural(n, 'lançamento', 'lançamentos')} desta importação do Extrato?</p>"
                 f"<p class='fin-hist-dica'>Arquivo: <b>{arquivo}</b>. Os lançamentos que você editou depois também "
                 "são apagados. Depois de desfazer, o arquivo pode ser importado de novo.</p>")
    st.html('<div class="dlg-rodape-linha"></div>')
    cancelar, confirmar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key="fin_hist_desf_nao"):
        st.session_state.pop("fin_hist_desf", None)
        st.rerun()
    if confirmar.button("Desfazer importação", type="primary", width="stretch", key="fin_hist_desf_sim"):
        apagados = repo.desfazer_importacao(estado["id"])
        st.session_state.pop("fin_hist_desf", None)
        comum.avisar("Esta importação já foi desfeita." if apagados is None
                     else _plural(apagados, "lançamento removido", "lançamentos removidos"))
        st.rerun()
