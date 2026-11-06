"""Revisão da importação: uma janela por cima da aba, com resumo, tabela editável e confirmação.

A janela (st.dialog) reexecuta só a própria função a cada edição. As linhas originais ficam em
estado["revisao"]["linhas"] e o que o usuário muda na tabela é lido do editor a cada execução, sem
realimentar o mesmo editor. A janela existe enquanto estado["revisao"] existir; fechar no X a descarta."""

from dataclasses import replace

import pandas as pd
import streamlit as st

from database.dinheiro import fmt_brl
from database.financas import calculos as calc
from database.financas import importacao as imp
from database.financas import linhas as lin
from database.financas import repo
from database.financas import sugestoes as sug
from modules.financas import comum
from modules.ui import plural

ESTADO = "fin_imp"
TIPO_ROTULO = {"fixo": "Fixo", "variavel": "Variável"}
_TIPO_POR_ROTULO = {v: k for k, v in TIPO_ROTULO.items()}


def _contexto(fim):
    """Regras, histórico e categorias do usuário para a sugestão automática."""
    lancamentos = repo.lancamentos_para_sugestao()
    historico = {}
    # Do mais recente para o mais antigo: o primeiro de cada descrição vale.
    for linha in lancamentos:
        historico.setdefault(imp.normalizar(linha["descricao"]), {"categoria_id": linha["categoria_id"], "tipo": linha["tipo"]})
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
    """Lê o arquivo no intervalo e monta a revisão. Nada é gravado."""
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


def _situacao(linha):
    if linha.situacao == "novo":
        return ""
    if linha.situacao == "duplicado":
        return "Já existe"
    return f"{'Ignorado' if linha.situacao == 'ignorado' else 'Erro'} · {linha.motivo}"


def tabela(linhas, nomes_categoria, entrada):
    """DataFrame do editor, com o `indice` da linha como índice. `nomes_categoria` é {id: nome}."""
    colunas = {
        "Importar": [linha.importar for linha in linhas],
        "Data": [linha.data for linha in linhas],
        "Descrição": [linha.descricao for linha in linhas],
        "Valor": [fmt_brl(linha.valor, sinal=True) if entrada else fmt_brl(-linha.valor) for linha in linhas],
    }
    if not entrada:
        colunas["Tipo"] = [TIPO_ROTULO.get(linha.tipo, "Variável") for linha in linhas]
    colunas["Categoria"] = [nomes_categoria.get(linha.categoria_id, "—") for linha in linhas]
    colunas["Situação"] = [_situacao(linha) for linha in linhas]
    return pd.DataFrame(colunas, index=[linha.indice for linha in linhas])


def _vazio(v):
    return v is None or (not isinstance(v, str) and bool(pd.isna(v)))


def aplicar_edicoes(linhas, editado, ids_por_nome, entrada):
    """Linhas com o que o usuário mudou no editor. Duplicadas e com erro nunca ficam marcadas para importar."""
    novas = []
    for linha in linhas:
        editada = editado.loc[linha.indice]
        descricao = "" if _vazio(editada["Descrição"]) else str(editada["Descrição"]).strip()[:calc.DESCRICAO_MAX]
        ligado = not _vazio(editada["Importar"]) and bool(editada["Importar"])
        tipo = "entrada" if entrada else _TIPO_POR_ROTULO.get(editada["Tipo"], linha.tipo)
        novas.append(replace(
            linha, descricao=descricao, tipo=tipo, categoria_id=ids_por_nome.get(editada["Categoria"], linha.categoria_id),
            importar=ligado and linha.situacao in lin.SITUACOES_GRAVAVEIS,
        ))
    return novas


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
    nomes = dict(rev["cats_entrada" if entrada else "cats_gasto"])
    ids = {nome: i for i, nome in nomes.items()}
    editado = st.data_editor(
        tabela(linhas_secao, nomes, entrada), key=f"fin_rev_{chave}", hide_index=True, width="stretch",
        height=min(40 + 35 * len(linhas_secao), 380), num_rows="fixed",
        column_config=_config_colunas(nomes, entrada, any(linha.situacao != "novo" for linha in linhas_secao)),
        disabled=["Data", "Valor", "Situação"],
    )
    return aplicar_edicoes(linhas_secao, editado, ids, entrada)


def _resumo_html(r):
    totais = []
    if r["saidas"]:
        totais.append(f'Saídas {fmt_brl(-r["saidas"])}')
    if r["entradas"]:
        totais.append(f'Entradas {fmt_brl(r["entradas"], sinal=True)}')
    pills = []
    if r["duplicados"]:
        pills.append(f'<i class="alerta">{plural(r["duplicados"], "já existe", "já existem")}</i>')
    if r["ignorados"]:
        pills.append(f'<i>{plural(r["ignorados"], "ignorado", "ignorados")}</i>')
    if r["erros"]:
        pills.append(f'<i class="erro">{r["erros"]} com erro</i>')
    return (f'<div class="fin-rev-resumo"><div class="fin-rev-total"><b>{r["a_importar"]} para importar</b>'
            f'<span>{" · ".join(totais) or "Nada marcado"}</span></div>'
            f'<div class="fin-rev-pills">{"".join(pills)}</div></div>')


def _gravar(rev, finais, resumo, regras, concluir):
    gravaveis = [linha for linha in finais if linha.importar and linha.situacao in lin.SITUACOES_GRAVAVEIS]
    if any(linha.categoria_id is None for linha in gravaveis):
        st.error("Há linhas sem categoria: escolha uma antes de importar.")
        return
    meta = {
        "arquivo": rev["arquivo"], "banco_id": rev["banco_id"], "origem": rev["origem"],
        "observacao": st.session_state.get("fin_imp_obs", ""), "periodo_inicio": rev["inicio"],
        "periodo_fim": rev["fim"], "qtd_lidas": len(finais), "qtd_duplicadas": resumo["duplicados"],
        "qtd_ignoradas": sum(1 for linha in finais if linha.situacao == "ignorado" and not linha.importar),
    }
    try:
        repo.registrar_importacao(meta, lin.para_lancamentos(finais, rev["banco_id"]))
    except repo.CategoriaIncompativel:
        st.error("Uma das categorias não serve para o tipo da linha. Confira a coluna Categoria.")
        return
    # Só depois de gravar com sucesso.
    for (descricao, _), regra in regras.items():
        repo.lembrar_regra(descricao, regra["categoria_id"], regra["tipo"])
    partes = [plural(len(gravaveis), "lançamento importado", "lançamentos importados")]
    if meta["qtd_duplicadas"]:
        partes.append(plural(meta["qtd_duplicadas"], "já existia", "já existiam"))
    if meta["qtd_ignoradas"]:
        partes.append(plural(meta["qtd_ignoradas"], "ignorado", "ignorados"))
    if regras:
        partes.append(plural(len(regras), "regra lembrada", "regras lembradas"))
    comum.avisar(" · ".join(partes))
    concluir()


def _descartar():
    """Fechar a janela no X (ou com Esc) descarta a revisão, como o Cancelar."""
    estado = st.session_state.get(ESTADO)
    if estado:
        estado["revisao"] = None


@st.dialog("Revisar importação", width="large", on_dismiss=_descartar)
def _dialogo(estado, concluir):
    rev = estado["revisao"]
    if rev is None:  # descartada em outra execução
        st.rerun()
    resumo_caixa = st.container()
    secoes = [(chave, titulo, entrada, [linha for linha in rev["linhas"] if linha.entrada == entrada])
              for chave, titulo, entrada in (("saidas", "Saídas", False), ("entradas", "Entradas", True))]
    secoes = [s for s in secoes if s[3]]
    st.caption("Edite a descrição, a categoria e o tipo direto na tabela e desmarque o que não quer importar.")
    abas = st.tabs([f"{titulo} ({len(linhas)})" for _, titulo, _, linhas in secoes]) if len(secoes) > 1 else [st.container()]
    finais = []
    for aba, (chave, _, entrada, linhas) in zip(abas, secoes):
        with aba:
            finais += _editor(rev, chave, linhas, entrada)
    finais.sort(key=lambda linha: linha.indice)
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
    if confirmar.button(f"Importar {plural(n, 'lançamento', 'lançamentos')}", type="primary", width="stretch",
                        icon=":material/check:", disabled=n == 0, key="fin_rev_confirmar"):
        regras = {}
        if lembrar:
            finais, regras = lin.lembrar_escolhas(rev["linhas"], finais)
        _gravar(rev, finais, resumo, regras, concluir)


def abrir(estado, concluir):
    """Abre a janela de revisão de estado["revisao"]. `concluir()` limpa a tela depois de gravar."""
    _dialogo(estado, concluir)
