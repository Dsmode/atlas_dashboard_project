"""Diálogo da engrenagem: categorias, bancos e saldo inicial.

O catálogo grava na hora (como o de categorias das Metas); o estado do diálogo (seção, item em edição,
aviso) fica em session_state["fin_cfg"], montado em `abrir()` antes de o diálogo existir. Fechar reexecuta
a página para o Extrato e o Dashboard refletirem as mudanças.
"""
from html import escape

import streamlit as st
from streamlit.errors import StreamlitInvalidLayoutContextError

from database import financas_calculos as calc
from database import financas_repo as repo
from modules.financas import comum

SECOES = {"categorias": "Categorias", "bancos": "Bancos", "geral": "Geral"}
TIPOS_CATEGORIA = {"gasto": "Gastos", "entrada": "Entradas"}
NOME_MAX = 30
SIGLA_MAX = 3
_DICA_OUTROS = "Recebe os lançamentos das categorias excluídas: não pode ser excluída."


def _uso(n):
    return "sem lançamentos" if n == 0 else ("1 lançamento" if n == 1 else f"{n} lançamentos")


def _mudar(cfg, modo=None, aviso=None):
    """Troca o item em edição/exclusão e reexecuta só o diálogo."""
    cfg["modo"] = modo
    if aviso:
        cfg["aviso"] = aviso
    try:
        st.rerun(scope="fragment")
    except StreamlitInvalidLayoutContextError:
        # fora de uma reexecução do diálogo (ex.: AppTest, que sempre roda o script inteiro)
        st.rerun()


def _aviso(cfg):
    texto = cfg.pop("aviso", None)
    if texto:
        comum.md(f'<div class="fin-cfg-ok">{comum.icone("check_circle")}{escape(texto)}</div>')


def _confirmacao(cfg, chave, nome, texto, excluir):
    """Caixa de confirmação logo abaixo do item: aviso + Cancelar/Excluir. `excluir()` devolve o aviso."""
    n = cfg["nonce"]
    with st.container(key=f"fin_cfg_conf_{n}_{chave}"):
        comum.md(f'<div class="fin-cfg-alerta">{comum.icone("warning")}<span>Excluir <b>{escape(nome)}</b>? '
            f'{escape(texto)}</span></div>')
        cancelar, confirmar = st.columns(2)
        if cancelar.button("Cancelar", width="stretch", key=f"fin_cfg_xno_{n}_{chave}"):
            _mudar(cfg)
        if confirmar.button("Excluir", type="primary", width="stretch", key=f"fin_cfg_xsim_{n}_{chave}"):
            _mudar(cfg, aviso=excluir())


def _botoes_item(cfg, chave, visivel=None, excluir=True):
    """Grupo de ações do item: editar, ocultar/mostrar (bancos) e excluir."""
    n = cfg["nonce"]
    clicado = None
    with st.container(horizontal=True, gap="xsmall", width="content", key=f"fin_cfg_acoes_{n}_{chave}"):
        if st.button("", icon=":material/edit:", help="Editar", key=f"fin_cfg_bed_{n}_{chave}"):
            clicado = "editar"
        if visivel is not None and st.button(
            "", icon=":material/visibility_off:" if visivel else ":material/visibility:",
            help="Ocultar do formulário" if visivel else "Mostrar no formulário", key=f"fin_cfg_bvis_{n}_{chave}",
        ):
            clicado = "visivel"
        if excluir and st.button("", icon=":material/delete:", help="Excluir", key=f"fin_cfg_bdel_{n}_{chave}"):
            clicado = "excluir"
    return clicado


def _salvar_cancelar(cfg, sufixo):
    """Cancelar / Salvar do formulário em linha; devolve True se clicou em Salvar."""
    cancelar, salvar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key=f"fin_cfg_fno_{sufixo}"):
        _mudar(cfg)
    return salvar.button("Salvar", type="primary", width="stretch", key=f"fin_cfg_fsim_{sufixo}")


# ---------- categorias ----------

def _form_categoria(cfg, tipo, categoria=None):
    sufixo = f"{cfg['nonce']}_{categoria['id'] if categoria else 'nova_' + tipo}"
    with st.container(key=f"fin_cfg_form_{sufixo}"):
        col_nome, col_cor = st.columns([5, 1], vertical_alignment="bottom")
        nome = col_nome.text_input(
            "Nome da categoria", value=categoria["nome"] if categoria else "", max_chars=NOME_MAX,
            key=f"fin_cfg_in_nome_{sufixo}",
        ).strip()
        cor = col_cor.color_picker(
            "Cor", value=comum.cor(categoria["cor"]) if categoria else comum.COR_PADRAO, key=f"fin_cfg_in_cor_{sufixo}",
        )
        if not _salvar_cancelar(cfg, sufixo):
            return
        if not nome:
            st.error("Dê um nome à categoria.")
            return
        try:
            if categoria:
                repo.atualizar_categoria(categoria["id"], nome, comum.cor(cor))
            else:
                repo.criar_categoria(tipo, nome, comum.cor(cor))
        except repo.NomeDuplicado:
            st.error(f"Já existe uma categoria de {tipo} chamada “{comum.texto_markdown(nome)}” "
                     "(maiúsculas e acentos não contam).")
            return
        _mudar(cfg, aviso="Categoria salva." if categoria else f"Categoria “{nome}” criada.")


def _secao_categorias(cfg):
    n = cfg["nonce"]
    tipo = comum.escolha(TIPOS_CATEGORIA, f"fin_cfg_tipo_{n}", cfg["tipo"], "Tipo de categoria")
    if tipo != cfg["tipo"]:
        cfg["tipo"], cfg["modo"] = tipo, None
    categorias = repo.listar_categorias(tipo)
    outros = next((c for c in categorias if c["protegida"]), None)
    nome_outros = outros["nome"] if outros else "Outros"

    for c in categorias:
        modo = cfg["modo"]
        if modo == ("cat_editar", c["id"]):
            _form_categoria(cfg, tipo, c)
            continue
        # "Outros" recebe os lançamentos das excluídas: cadeado no lugar do botão de excluir
        cadeado = comum.icone("lock", "fin-cfg-cadeado") if c["protegida"] else ""
        dica = f' title="{_DICA_OUTROS}"' if c["protegida"] else ""
        with st.container(horizontal=True, vertical_alignment="center", gap="small",
                          key=f"fin_cfg_lin_c_{n}_{c['id']}"):
            comum.md(f'<div class="fin-cfg-item"{dica}>'
                f'<span class="fin-cfg-ponto" style="--cor:{comum.cor(c["cor"])}"></span>'
                f'<span class="fin-cfg-nome">{escape(c["nome"])}</span>{cadeado}'
                f'<span class="fin-cfg-uso">{_uso(c["em_uso"])}</span></div>', width="stretch")
            clicado = _botoes_item(cfg, f"c{c['id']}", excluir=not c["protegida"])
        if clicado == "editar":
            _mudar(cfg, ("cat_editar", c["id"]))
        if clicado == "excluir":
            _mudar(cfg, ("cat_excluir", c["id"]))
        if modo == ("cat_excluir", c["id"]):
            em_uso = c["em_uso"]
            texto = ("Nenhum lançamento usa esta categoria." if em_uso == 0 else
                     f"1 lançamento irá para {nome_outros}." if em_uso == 1 else
                     f"{em_uso} lançamentos irão para {nome_outros}.")

            def excluir(categoria_id=c["id"]):
                movidos = repo.excluir_categoria(categoria_id)
                if not movidos:
                    return "Categoria excluída."
                return f"Categoria excluída. {_uso(movidos)} movido{'s' if movidos > 1 else ''} para {nome_outros}."

            _confirmacao(cfg, f"c{c['id']}", c["nome"], texto, excluir)

    if not categorias:
        comum.vazio("Nenhuma categoria ainda.")
    if cfg["modo"] == "cat_nova":
        _form_categoria(cfg, tipo)
    elif st.button("Adicionar categoria", icon=":material/add:", width="stretch", key=f"fin_cfg_add_c_{n}"):
        _mudar(cfg, "cat_nova")


# ---------- bancos ----------

def _form_banco(cfg, banco=None):
    sufixo = f"{cfg['nonce']}_b{banco['id'] if banco else 'novo'}"
    with st.container(key=f"fin_cfg_form_{sufixo}"):
        col_nome, col_sigla, col_cor = st.columns([4, 2, 1], vertical_alignment="bottom")
        nome = col_nome.text_input(
            "Nome do banco", value=banco["nome"] if banco else "", max_chars=NOME_MAX, key=f"fin_cfg_in_bnome_{sufixo}",
        ).strip()
        sigla = col_sigla.text_input(
            "Sigla", value=(banco["sigla"] or "") if banco else "", max_chars=SIGLA_MAX, placeholder="Ex.: Nu",
            key=f"fin_cfg_in_sigla_{sufixo}", help="Até 3 letras, no lugar da logo",
        ).strip()
        cor = col_cor.color_picker(
            "Cor", value=comum.cor(banco["cor"]) if banco else comum.COR_PADRAO, key=f"fin_cfg_in_bcor_{sufixo}",
        )
        if not _salvar_cancelar(cfg, sufixo):
            return
        if not nome:
            st.error("Dê um nome ao banco.")
            return
        if not sigla:
            st.error("Informe a sigla (até 3 letras).")
            return
        try:
            if banco:
                repo.atualizar_banco(banco["id"], nome, sigla, comum.cor(cor))
            else:
                repo.criar_banco(nome, sigla, comum.cor(cor))
        except repo.NomeDuplicado:
            st.error(f"Já existe um banco chamado “{comum.texto_markdown(nome)}” (maiúsculas e acentos não contam).")
            return
        _mudar(cfg, aviso="Banco salvo." if banco else f"Banco “{nome}” adicionado.")


def _secao_bancos(cfg):
    n = cfg["nonce"]
    st.caption("Banco oculto some do formulário de lançamento; os lançamentos antigos continuam mostrando o banco.")
    bancos = repo.listar_bancos(incluir_ocultos=True)
    for b in bancos:
        modo = cfg["modo"]
        if modo == ("banco_editar", b["id"]):
            _form_banco(cfg, b)
            continue
        oculto = '' if b["ativo"] else '<span class="fin-selo">Oculto</span>'
        with st.container(horizontal=True, vertical_alignment="center", gap="small",
                          key=f"fin_cfg_lin_b_{n}_{b['id']}"):
            comum.md(f'<div class="fin-cfg-item{"" if b["ativo"] else " inativo"}">'
                f'{comum.selo_banco(b["sigla"], b["nome"], b["cor"])}{oculto}'
                f'<span class="fin-cfg-uso">{_uso(b["em_uso"])}</span></div>', width="stretch")
            clicado = _botoes_item(cfg, f"b{b['id']}", visivel=bool(b["ativo"]))
        if clicado == "editar":
            _mudar(cfg, ("banco_editar", b["id"]))
        if clicado == "visivel":
            repo.definir_banco_ativo(b["id"], not b["ativo"])
            _mudar(cfg, aviso=f"{b['nome']} {'oculto do formulário' if b['ativo'] else 'de volta ao formulário'}.")
        if clicado == "excluir":
            _mudar(cfg, ("banco_excluir", b["id"]))
        if modo == ("banco_excluir", b["id"]):
            em_uso = b["em_uso"]
            texto = ("Nenhum lançamento usa este banco." if em_uso == 0 else
                     "1 lançamento ficará sem banco." if em_uso == 1 else
                     f"{em_uso} lançamentos ficarão sem banco.")
            if b["ativo"]:
                texto += " Para tirar só do formulário, oculte o banco."

            def excluir(banco_id=b["id"]):
                afetados = repo.excluir_banco(banco_id)
                return f"Banco excluído. {_uso(afetados).capitalize()} ficou sem banco." if afetados == 1 else (
                    f"Banco excluído. {afetados} lançamentos ficaram sem banco." if afetados else "Banco excluído.")

            _confirmacao(cfg, f"b{b['id']}", b["nome"], texto, excluir)

    if not bancos:
        comum.vazio("Nenhum banco ainda.")
    if cfg["modo"] == "banco_novo":
        _form_banco(cfg)
    elif st.button("Adicionar banco", icon=":material/add:", width="stretch", key=f"fin_cfg_add_b_{n}"):
        _mudar(cfg, "banco_novo")


# ---------- geral ----------

def _secao_geral(cfg):
    n = cfg["nonce"]
    saldo = repo.obter_saldo_inicial()
    versao = cfg.setdefault("saldo_versao", 0)  # muda a cada gravação: o campo volta com o valor do banco
    comum.secao("account_balance", "Saldo inicial")
    st.caption("Quanto você tinha antes do primeiro lançamento: é o ponto de partida do fluxo de caixa. "
               "Pode ser negativo (ex.: começou devendo).")
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small", key=f"fin_cfg_saldo_{n}"):
        numero = st.number_input(
            "Saldo inicial (R$)", value=float(saldo), min_value=-float(calc.VALOR_MAX),
            max_value=float(calc.VALOR_MAX), step=0.01, format="%.2f", key=f"fin_cfg_in_saldo_{n}_{versao}",
            width="stretch",
        )
        salvar = st.button("Salvar", type="primary", key=f"fin_cfg_saldo_ok_{n}")
    if salvar:
        valor = calc.para_decimal(numero)
        if abs(valor) > calc.VALOR_MAX:
            st.error("Valor alto demais.")
            return
        repo.definir_saldo_inicial(valor)
        cfg["saldo_versao"] = versao + 1
        _mudar(cfg, aviso=f"Saldo inicial salvo: {calc.fmt_brl(valor)}.")


# ---------- diálogo ----------

def abrir():
    n = st.session_state.get("fin_cfg_nonce", 0) + 1
    st.session_state.fin_cfg_nonce = n
    st.session_state.fin_cfg = {"nonce": n, "secao": "categorias", "tipo": "gasto", "modo": None, "aviso": None}
    _dialogo()


@st.dialog("Configurações de finanças", width="large", on_dismiss="rerun")
def _dialogo():
    cfg = st.session_state.fin_cfg
    n = cfg["nonce"]
    secao = comum.escolha(SECOES, f"fin_cfg_secao_{n}", cfg["secao"], "Seção")
    if secao != cfg["secao"]:
        cfg["secao"], cfg["modo"] = secao, None
    _aviso(cfg)
    with st.container(key=f"fin_cfg_corpo_{n}"):
        {"categorias": _secao_categorias, "bancos": _secao_bancos, "geral": _secao_geral}[secao](cfg)
    st.html('<div class="dlg-rodape-linha"></div>')
    if st.button("Fechar", width="stretch", key=f"fin_cfg_fechar_{n}"):
        st.rerun()
