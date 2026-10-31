"""Diálogos do Extrato: editar, excluir e copiar os gastos fixos do mês anterior.

Os diálogos do Streamlit reexecutam só a própria função: o estado inicial é montado em `abrir_*`, antes de
abrir, e o nonce na chave dos campos garante que cada abertura comece do zero.
"""
import streamlit as st

from database import financas_calculos as calc
from database import financas_repo as repo
from modules.financas import comum
from modules.financas.extrato import formulario


def _plural(n, texto):
    """'gasto fixo copiado' → 'gastos fixos copiados' quando n > 1."""
    return texto if n == 1 else " ".join(p + "s" for p in texto.split())


# ---------- editar e excluir ----------

def abrir_edicao(lancamento):
    n = st.session_state.get("fin_ext_edit_n", 0) + 1
    st.session_state.fin_ext_edit_n = n
    st.session_state.fin_ext_edicao = {"nonce": n, "lancamento": lancamento}
    _dialogo_edicao()


@st.dialog("Editar lançamento", width="medium")
def _dialogo_edicao():
    estado = st.session_state.fin_ext_edicao
    lancamento, n = estado["lancamento"], estado["nonce"]
    categorias = repo.listar_categorias()
    # banco oculto só aparece se for o do próprio lançamento (os antigos continuam mostrando o banco)
    bancos = [b for b in repo.listar_bancos(incluir_ocultos=True) if b["ativo"] or b["id"] == lancamento["banco_id"]]

    dados, categoria = formulario.campos(f"fin_edt_{n}", lancamento, categorias, bancos)
    st.html('<div class="dlg-rodape-linha"></div>')
    cancelar, salvar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key=f"fin_edt_cancelar_{n}"):
        st.rerun()
    if salvar.button("Salvar", type="primary", width="stretch", key=f"fin_edt_salvar_{n}"):
        erro = formulario.validar(dados, categoria)
        if erro:
            st.error(erro)
            return
        gravou, existia = formulario.gravar(repo.atualizar_lancamento, lancamento["id"], dados)
        if not gravou:
            return
        destino = calc.inicio_mes(dados["data"])
        if not existia:
            comum.avisar("Esse lançamento já tinha sido excluído.")
        elif destino == calc.inicio_mes(lancamento["data"]):
            comum.avisar("Lançamento atualizado.")
        else:
            comum.avisar(f"Lançamento atualizado e movido para {calc.nome_mes(destino)}.")
        st.rerun()


@st.dialog("Excluir lançamento")
def dialogo_exclusao(lancamento):
    comum.md(
        f'<div class="fin-ext-confirma">{comum.descricao_html(lancamento)}'
        f'<div class="fin-ext-confirma-dados"><span>{lancamento["data"]:%d/%m/%Y}</span>'
        f'{comum.valor_html(lancamento)}</div></div>'
        '<p class="fin-ext-confirma-txt">Excluir este lançamento? Não dá para desfazer.</p>'
    )
    cancelar, excluir = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key="fin_exc_cancelar"):
        st.rerun()
    if excluir.button("Excluir", type="primary", width="stretch", key="fin_exc_ok"):
        repo.excluir_lancamento(lancamento["id"])
        comum.avisar("Lançamento excluído.")
        st.rerun()


# ---------- copiar gastos fixos do mês anterior ----------

def abrir_copia(mes):
    anterior = calc.somar_meses(mes, -1)
    plano = calc.plano_copia_fixos(
        repo.listar_lancamentos(anterior, calc.fim_mes(anterior), "fixo"),
        repo.listar_lancamentos(mes, calc.fim_mes(mes), "fixo"),
        mes,
    )
    n = st.session_state.get("fin_ext_copia_n", 0) + 1
    st.session_state.fin_ext_copia_n = n
    st.session_state.fin_ext_copia = {"nonce": n, "mes": mes, "anterior": anterior, "plano": plano}
    _dialogo_copia()


def _linha_copia(item):
    nota = '<span class="fin-ext-repetido">já existe neste mês</span>' if item["repetido"] else ""
    return (
        f'<div class="fin-ext-copia-linha"><span class="fin-ext-data">{item["data"]:%d/%m}</span>'
        f'{comum.descricao_html(item)}<span class="fin-ext-forma" title="{comum.FORMA_ROTULO[item["forma"]]}">'
        f'{comum.forma_html(item["forma"])}</span>'
        f'<span class="fin-ext-banco">{comum.banco_html(item)}</span>'
        f'<span class="fin-ext-valor">{comum.valor_html(item)}{nota}</span></div>'
    )


@st.dialog("Copiar gastos fixos", width="large")
def _dialogo_copia():
    estado = st.session_state.fin_ext_copia
    n, mes, plano = estado["nonce"], estado["mes"], estado["plano"]
    if not plano:
        comum.vazio(f"Nenhum gasto fixo em {calc.nome_mes(estado['anterior'])} para copiar.")
        if st.button("Fechar", width="stretch", key=f"fin_cop_fechar_{n}"):
            st.rerun()
        return

    comum.md(f'<p class="fin-ext-copia-intro">Gastos fixos de <b>{calc.nome_mes(estado["anterior"])}</b> que vão '
             f'para <b>{calc.nome_mes(mes)}</b>, no mesmo dia. Desmarque o que não quiser; depois é só ajustar '
             'pela lista.</p>')
    with st.container(key="fin_cop_lista"):
        for i, item in enumerate(plano):
            with st.container(horizontal=True, vertical_alignment="center", gap=None, key=f"fin_cop_lin_{n}_{i}"):
                st.checkbox("Copiar", value=not item["repetido"], key=f"fin_cop_chk_{n}_{i}",
                            label_visibility="collapsed", width="content")
                comum.md(_linha_copia(item), width="stretch")
    marcados = [item for i, item in enumerate(plano) if st.session_state.get(f"fin_cop_chk_{n}_{i}")]

    st.html('<div class="dlg-rodape-linha"></div>')
    cancelar, copiar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key=f"fin_cop_cancelar_{n}"):
        st.rerun()
    if copiar.button(f"Copiar {len(marcados)}", type="primary", width="stretch", disabled=not marcados,
                     icon=":material/content_copy:", key=f"fin_cop_ok_{n}"):
        gravou, copiados = formulario.gravar(repo.criar_lancamentos, [
            {"tipo": "fixo", "data": item["data"], "descricao": item["descricao"],
             "categoria_id": item["categoria_id"], "valor": item["valor"], "forma": item["forma"],
             "banco_id": item["banco_id"], "observacao": item["observacao"]}
            for item in marcados
        ])
        if not gravou:
            return
        comum.avisar(f"{copiados} {_plural(copiados, 'gasto fixo copiado')} para {calc.nome_mes(mes)}.")
        st.rerun()
