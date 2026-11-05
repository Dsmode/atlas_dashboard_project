"""Revisão da importação: uma janela por cima da aba com o resumo, a tabela editável e a confirmação.

A janela (st.dialog) reexecuta só a própria função a cada edição; as linhas originais ficam em
`estado["revisao"]["linhas"]` e o que o usuário muda na tabela é lido do editor a cada execução (nunca realimentado
no mesmo editor). Existe uma janela aberta enquanto `estado["revisao"]` existir; fechar no X a descarta.
"""
from dataclasses import replace

import pandas as pd
import streamlit as st

from database import financas_calculos as calc
from database import financas_importacao as imp
from database import financas_linhas as lin
from database import financas_repo as repo
from database import financas_sugestoes as sug
from modules.financas import comum

ESTADO = "fin_imp"
TIPO_ROTULO = {"fixo": "Fixo", "variavel": "Variável"}
_TIPO_POR_ROTULO = {v: k for k, v in TIPO_ROTULO.items()}


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


# ---------- montagem ----------

def _contexto(fim):
    """Regras, histórico e categorias do usuário para a sugestão automática."""
    lancamentos = repo.lancamentos_para_sugestao()
    historico = {}
    for l in lancamentos:  # do mais recente para o mais antigo: o primeiro de cada descrição vale
        historico.setdefault(imp.normalizar(l["descricao"]), {"categoria_id": l["categoria_id"], "tipo": l["tipo"]})
    gasto, entrada = {}, {}
    for destino, tipo in ((gasto, "gasto"), (entrada, "entrada")):
        for c in repo.listar_categorias(tipo):
            destino[imp.normalizar(c["nome"])] = c["id"]
            if c["protegida"]:
                destino[sug.OUTROS] = c["id"]  # a "Outros" vale mesmo renomeada
    return sug.Contexto(
        regras=tuple(repo.listar_regras()), historico=historico,
        recorrentes=sug.recorrentes(lancamentos, calc.inicio_mes(fim)),
        categorias_gasto=gasto, categorias_entrada=entrada,
    )


def construir(estado, assinatura):
    """Lê o arquivo no intervalo e monta a revisão (nada é gravado)."""
    _, banco_id, inicio, fim = assinatura
    extrato = estado["extrato"]
    compras = lin.preparar_compras(extrato, inicio, fim)
    existentes = repo.chaves_existentes(banco_id, [imp.chave_externa(c.principal) for c in compras])
    linhas = lin.montar_linhas(compras, extrato.origem, repo.obter_meu_nome(), _contexto(fim), existentes)
    return {
        "assinatura": assinatura, "linhas": linhas, "banco_id": banco_id, "inicio": inicio, "fim": fim,
        "origem": extrato.origem, "arquivo": estado["nome"],
        "cats_gasto": [(c["id"], c["nome"]) for c in repo.listar_categorias("gasto")],
        "cats_entrada": [(c["id"], c["nome"]) for c in repo.listar_categorias("entrada")],
    }


# ---------- tabela <-> linhas ----------

def _situacao(l):
    if l.situacao == "novo":
        return ""
    if l.situacao == "duplicado":
        return "Já existe"
    return f"{'Ignorado' if l.situacao == 'ignorado' else 'Erro'} · {l.motivo}"


def tabela(linhas, nomes_categoria, entrada):
    """DataFrame do editor (índice = `indice` da linha). `nomes_categoria`: {id: nome}."""
    colunas = {
        "Importar": [l.importar for l in linhas],
        "Data": [l.data for l in linhas],
        "Descrição": [l.descricao for l in linhas],
        "Valor": [calc.fmt_brl(l.valor, sinal=True) if entrada else calc.fmt_brl(-l.valor) for l in linhas],
    }
    if not entrada:
        colunas["Tipo"] = [TIPO_ROTULO.get(l.tipo, "Variável") for l in linhas]
    colunas["Categoria"] = [nomes_categoria.get(l.categoria_id, "—") for l in linhas]
    colunas["Situação"] = [_situacao(l) for l in linhas]
    return pd.DataFrame(colunas, index=[l.indice for l in linhas])


def _vazio(v):
    return v is None or (not isinstance(v, str) and bool(pd.isna(v)))


def aplicar_edicoes(linhas, editado, ids_por_nome, entrada):
    """Linhas com o que o usuário mudou no editor; duplicadas e com erro nunca ficam marcadas para importar."""
    novas = []
    for l in linhas:
        linha = editado.loc[l.indice]
        descricao = "" if _vazio(linha["Descrição"]) else str(linha["Descrição"]).strip()[:calc.DESCRICAO_MAX]
        ligado = not _vazio(linha["Importar"]) and bool(linha["Importar"])
        tipo = "entrada" if entrada else _TIPO_POR_ROTULO.get(linha["Tipo"], l.tipo)
        novas.append(replace(
            l, descricao=descricao, tipo=tipo, categoria_id=ids_por_nome.get(linha["Categoria"], l.categoria_id),
            importar=ligado and l.situacao in lin.SITUACOES_GRAVAVEIS,
        ))
    return novas


# ---------- janela ----------

def _config_colunas(nomes_categoria, entrada, com_situacao):
    cfg = {
        "Importar": st.column_config.CheckboxColumn("Importar", width="small"),
        "Data": st.column_config.DateColumn("Data", format="DD/MM", width="small"),
        "Descrição": st.column_config.TextColumn("Descrição", max_chars=calc.DESCRICAO_MAX, width="large"),
        "Valor": st.column_config.TextColumn("Valor", width="small"),
        "Categoria": st.column_config.SelectboxColumn("Categoria", options=list(nomes_categoria.values()),
                                                       required=True, width="medium"),
        "Situação": st.column_config.TextColumn("Situação", width="medium") if com_situacao else None,
    }
    if not entrada:
        cfg["Tipo"] = st.column_config.SelectboxColumn("Tipo", options=list(TIPO_ROTULO.values()), required=True,
                                                        width="small")
    return cfg


def _editor(rev, chave, linhas_secao, entrada):
    """Tabela editável de uma seção; devolve as linhas dela com as edições."""
    nomes = dict(rev["cats_entrada" if entrada else "cats_gasto"])
    ids = {nome: i for i, nome in nomes.items()}
    editado = st.data_editor(
        tabela(linhas_secao, nomes, entrada), key=f"fin_rev_{chave}", hide_index=True, width="stretch",
        height=min(40 + 35 * len(linhas_secao), 380), num_rows="fixed",
        column_config=_config_colunas(nomes, entrada, any(l.situacao != "novo" for l in linhas_secao)),
        disabled=["Data", "Valor", "Situação"],
    )
    return aplicar_edicoes(linhas_secao, editado, ids, entrada)


def _resumo_html(r):
    totais = []
    if r["saidas"]:
        totais.append(f'Saídas {calc.fmt_brl(-r["saidas"])}')
    if r["entradas"]:
        totais.append(f'Entradas {calc.fmt_brl(r["entradas"], sinal=True)}')
    pills = []
    if r["duplicados"]:
        pills.append(f'<i class="alerta">{_plural(r["duplicados"], "já existe", "já existem")}</i>')
    if r["ignorados"]:
        pills.append(f'<i>{_plural(r["ignorados"], "ignorado", "ignorados")}</i>')
    if r["erros"]:
        pills.append(f'<i class="erro">{r["erros"]} com erro</i>')
    return (f'<div class="fin-rev-resumo"><div class="fin-rev-total"><b>{r["a_importar"]} para importar</b>'
            f'<span>{" · ".join(totais) or "Nada marcado"}</span></div>'
            f'<div class="fin-rev-pills">{"".join(pills)}</div></div>')


def _gravar(rev, finais, resumo, regras, concluir):
    gravaveis = [l for l in finais if l.importar and l.situacao in lin.SITUACOES_GRAVAVEIS]
    if any(l.categoria_id is None for l in gravaveis):
        st.error("Há linhas sem categoria: escolha uma antes de importar.")
        return
    meta = {
        "arquivo": rev["arquivo"], "banco_id": rev["banco_id"], "origem": rev["origem"],
        "observacao": st.session_state.get("fin_imp_obs", ""), "periodo_inicio": rev["inicio"],
        "periodo_fim": rev["fim"], "qtd_lidas": len(finais), "qtd_duplicadas": resumo["duplicados"],
        "qtd_ignoradas": sum(1 for l in finais if l.situacao == "ignorado" and not l.importar),
    }
    try:
        repo.registrar_importacao(meta, lin.para_lancamentos(finais, rev["banco_id"]))
    except repo.CategoriaIncompativel:
        st.error("Uma das categorias não serve para o tipo da linha. Confira a coluna Categoria.")
        return
    for (descricao, _), regra in regras.items():  # só depois de gravar com sucesso
        repo.lembrar_regra(descricao, regra["categoria_id"], regra["tipo"])
    partes = [_plural(len(gravaveis), "lançamento importado", "lançamentos importados")]
    if meta["qtd_duplicadas"]:
        partes.append(_plural(meta["qtd_duplicadas"], "já existia", "já existiam"))
    if meta["qtd_ignoradas"]:
        partes.append(_plural(meta["qtd_ignoradas"], "ignorado", "ignorados"))
    if regras:
        partes.append(_plural(len(regras), "regra lembrada", "regras lembradas"))
    comum.avisar(" · ".join(partes))
    concluir()


def _descartar():
    """Fechar a janela no X (ou Esc) descarta a revisão, como o Cancelar."""
    estado = st.session_state.get(ESTADO)
    if estado:
        estado["revisao"] = None


@st.dialog("Revisar importação", width="large", on_dismiss=_descartar)
def _dialogo(estado, concluir):
    rev = estado["revisao"]
    if rev is None:  # descartada em outra execução
        st.rerun()
    resumo_caixa = st.container()
    secoes = [(chave, titulo, entrada, [l for l in rev["linhas"] if l.entrada == entrada])
              for chave, titulo, entrada in (("saidas", "Saídas", False), ("entradas", "Entradas", True))]
    secoes = [s for s in secoes if s[3]]
    st.caption("Edite a descrição, a categoria e o tipo direto na tabela e desmarque o que não quer importar.")
    abas = st.tabs([f"{titulo} ({len(linhas)})" for _, titulo, _, linhas in secoes]) if len(secoes) > 1 else [st.container()]
    finais = []
    for aba, (chave, _, entrada, linhas) in zip(abas, secoes):
        with aba:
            finais += _editor(rev, chave, linhas, entrada)
    finais.sort(key=lambda l: l.indice)
    resumo = lin.resumo(finais)
    with resumo_caixa:
        comum.md(_resumo_html(resumo))

    st.html('<div class="dlg-rodape-linha"></div>')
    lembrar = st.checkbox(
        "Lembrar minhas escolhas nas próximas importações", key="fin_rev_lembrar",
        help="As categorias e tipos que você mudar viram regras (em Configurações › Regras) e valem também para "
             "as outras linhas iguais deste arquivo.",
    )
    cancelar, confirmar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key="fin_rev_cancelar"):
        estado["revisao"] = None
        st.rerun()
    n = resumo["a_importar"]
    if confirmar.button(f"Importar {_plural(n, 'lançamento', 'lançamentos')}", type="primary", width="stretch",
                        icon=":material/check:", disabled=n == 0, key="fin_rev_confirmar"):
        regras = {}
        if lembrar:
            finais, regras = lin.lembrar_escolhas(rev["linhas"], finais)
        _gravar(rev, finais, resumo, regras, concluir)


def abrir(estado, concluir):
    """Abre a janela de revisão de `estado["revisao"]` (`concluir()` limpa a tela depois de gravar)."""
    _dialogo(estado, concluir)
