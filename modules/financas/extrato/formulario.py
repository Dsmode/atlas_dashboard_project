"""Campos do lançamento (usados pelo formulário ↖ e pelo diálogo de edição) e o formulário de novo lançamento."""
from datetime import date

import streamlit as st

from database import financas_calculos as calc
from database import financas_repo as repo
from modules.financas import comum


def _data_padrao(mes):
    """Hoje, se hoje estiver no mês aberto; senão o dia 1 do mês aberto."""
    hoje = date.today()
    return hoje if calc.inicio_mes(hoje) == mes else mes


def _nome_banco(banco):
    if banco is None:
        return "Sem banco"
    return banco["nome"] + ("" if banco["ativo"] else " (oculto)")


def campos(prefixo, base, categorias, bancos):
    """Desenha os campos e devolve (dados para o repositório, categoria escolhida ou None).

    `base`: valores iniciais (tipo, data, descricao, categoria_id, valor, forma, banco_id, observacao).
    A chave da categoria leva o grupo (entrada/gasto): trocar Fixo ↔ Variável mantém a escolha."""
    tipo = comum.escolha(comum.TIPO_ROTULO, f"{prefixo}_tipo", base["tipo"], "Tipo do lançamento")
    grupo = calc.grupo_categoria(tipo)
    por_id = {c["id"]: c for c in categorias if c["tipo"] == grupo}
    ids_categoria = list(por_id)

    col1, col2 = st.columns(2)
    data = col1.date_input("Data", value=base["data"], format="DD/MM/YYYY", key=f"{prefixo}_data")
    numero = col2.number_input(
        "Valor (R$)", value=float(base["valor"]) if base["valor"] is not None else None, min_value=0.0,
        max_value=float(calc.VALOR_MAX), step=0.01, format="%.2f", placeholder="0,00", key=f"{prefixo}_valor",
    )

    col1, col2 = st.columns(2)
    descricao = col1.text_input(
        "Descrição", value=base["descricao"] or "", max_chars=calc.DESCRICAO_MAX, placeholder="Opcional",
        key=f"{prefixo}_desc",
    )
    categoria_id = col2.selectbox(
        "Categoria", ids_categoria,
        index=ids_categoria.index(base["categoria_id"]) if base["categoria_id"] in por_id else None,
        format_func=lambda i: por_id[i]["nome"], placeholder="Escolha a categoria", key=f"{prefixo}_cat_{grupo}",
    )

    col1, col2 = st.columns(2)
    forma = col1.selectbox(
        "Forma de pagamento", list(calc.FORMAS), index=list(calc.FORMAS).index(base["forma"]),
        format_func=comum.FORMA_ROTULO.get, key=f"{prefixo}_forma",
    )
    banco_id = None
    if forma == "dinheiro":
        col2.selectbox("Banco", ["Não se aplica"], disabled=True, key=f"{prefixo}_banco_din")
    else:
        # "Sem banco" é uma opção da lista: um selectbox com valor escolhido não volta a ficar vazio
        por_banco = {b["id"]: b for b in bancos}
        ids_banco = [None, *por_banco]
        banco_id = col2.selectbox(
            "Banco", ids_banco, index=ids_banco.index(base["banco_id"]) if base["banco_id"] in por_banco else 0,
            format_func=lambda i: _nome_banco(por_banco.get(i)), key=f"{prefixo}_banco",
        )

    observacao = st.text_input(
        "Observações", value=base["observacao"] or "", max_chars=calc.OBSERVACAO_MAX, placeholder="Opcional",
        key=f"{prefixo}_obs",
    )
    dados = {
        "tipo": tipo, "data": data, "descricao": descricao.strip(), "categoria_id": categoria_id,
        "valor": calc.para_decimal(numero) if numero is not None else None, "forma": forma, "banco_id": banco_id,
        "observacao": observacao.strip(),
    }
    return dados, por_id.get(categoria_id)


def validar(dados, categoria):
    if dados["data"] is None:
        return "Informe a data."
    erro = calc.validar_lancamento(
        dados["tipo"], dados["valor"], dados["forma"], dados["banco_id"],
        categoria["tipo"] if categoria else calc.grupo_categoria(dados["tipo"]),
        dados["descricao"], dados["observacao"],
    )
    if not erro and categoria is None:
        erro = "Escolha a categoria."
    return erro


def gravar(acao, *args):
    """Chama o repositório: (True, resultado), ou (False, None) com o erro na tela se a categoria sumiu
    (apagada em outra aba enquanto o formulário estava aberto)."""
    try:
        return True, acao(*args)
    except repo.CategoriaIncompativel:
        st.error("Essa categoria não existe mais. Escolha outra.")
        return False, None


# ---------- formulário (↖) ----------
# Fragmento: trocar o tipo ou a forma reexecuta só o formulário. Lançar com sucesso reexecuta a página
# (as listas mudam). Os campos levam um nonce na chave: depois de lançar, voltam vazios.

@st.fragment
def formulario(mes):
    n = st.session_state.setdefault("fin_ext_form_n", 0)
    ultimo = st.session_state.get("fin_ext_ultimo", {})
    base = {
        "tipo": ultimo.get("tipo", "variavel"), "data": _data_padrao(mes), "descricao": "", "categoria_id": None,
        "valor": None, "forma": ultimo.get("forma", "pix"), "banco_id": ultimo.get("banco_id"), "observacao": "",
    }
    categorias = repo.listar_categorias()
    bancos = repo.listar_bancos()  # só os ativos: banco oculto não aparece para lançamentos novos

    comum.cabecalho_cartao("Novo lançamento", "add_card")
    # o mês entra na chave para a data padrão acompanhar a troca de mês
    dados, categoria = campos(f"fin_lanc_{n}_{mes:%Y%m}", base, categorias, bancos)
    if st.button("Lançar", type="primary", icon=":material/check:", width="stretch", key=f"fin_lanc_ok_{n}"):
        erro = validar(dados, categoria)
        if erro:
            st.error(erro)
            return
        gravou, _ = gravar(repo.criar_lancamento, dados)
        if not gravou:
            return
        # tipo, forma e banco continuam escolhidos para o próximo lançamento (vários seguidos é o comum)
        st.session_state.fin_ext_ultimo = {"tipo": dados["tipo"], "forma": dados["forma"], "banco_id": dados["banco_id"]}
        st.session_state.fin_ext_form_n = n + 1
        destino = calc.inicio_mes(dados["data"])
        comum.avisar("Lançamento registrado." if destino == mes else
                     f"Lançamento registrado em {calc.nome_mes(destino)} (fora do mês aberto).")
        st.rerun()
