"""Diálogo da engrenagem: categorias, bancos, regras e dados gerais.

O catálogo grava na hora. O estado do diálogo (seção, item em edição, aviso) fica em
session_state["fin_cfg"], montado em `abrir()` antes de o diálogo existir. Ao fechar, a página roda de novo
para o Extrato e o Dashboard refletirem as mudanças."""

from html import escape

import streamlit as st
from streamlit.errors import StreamlitInvalidLayoutContextError

from database.cores import COR_PADRAO, cor_valida
from database.dinheiro import VALOR_MAX, fmt_brl
from database.financas import calculos as calc
from database.financas import repo
from database.texto import normalizar
from modules.financas import comum
from modules.ui import secao

SECOES = {"categorias": "Categorias", "bancos": "Bancos", "regras": "Regras", "geral": "Geral"}
TIPOS_CATEGORIA = {"gasto": "Gastos", "entrada": "Entradas"}
NOME_MAX = 30
SIGLA_MAX = 3
_DICA_OUTROS = "Recebe os lançamentos das categorias excluídas: não pode ser excluída."


def _uso(n):
    return "sem lançamentos" if n == 0 else ("1 lançamento" if n == 1 else f"{n} lançamentos")


def _mudar(cfg, modo=None, aviso=None):
    cfg["modo"] = modo
    if aviso:
        cfg["aviso"] = aviso
    try:
        st.rerun(scope="fragment")
    # Fora de uma reexecução de fragmento, como no AppTest, que sempre roda o script inteiro.
    except StreamlitInvalidLayoutContextError:
        st.rerun()


def _aviso(cfg):
    texto = cfg.pop("aviso", None)
    if texto:
        comum.md(f'<div class="fin-cfg-ok">{comum.icone("check_circle")}{escape(texto)}</div>')


def _confirmacao(cfg, chave, nome, texto, excluir):
    """Caixa de confirmação logo abaixo do item. `excluir()` faz a exclusão e devolve o aviso."""
    n = cfg["nonce"]
    with st.container(key=f"fin_cfg_conf_{n}_{chave}"):
        comum.md(f'<div class="fin-cfg-alerta">{comum.icone("warning")}<span>Excluir <b>{escape(nome)}</b>? '
            f'{escape(texto)}</span></div>')
        cancelar, confirmar = st.columns(2)
        if cancelar.button("Cancelar", width="stretch", key=f"fin_cfg_xno_{n}_{chave}"):
            _mudar(cfg)
        if confirmar.button("Excluir", type="primary", width="stretch", key=f"fin_cfg_xsim_{n}_{chave}"):
            _mudar(cfg, aviso=excluir())


def _botoes_item(cfg, chave, visivel=None, excluir=True, editar=True):
    n = cfg["nonce"]
    clicado = None
    with st.container(horizontal=True, gap="xsmall", width="content", key=f"fin_cfg_acoes_{n}_{chave}"):
        if editar and st.button("", icon=":material/edit:", help="Editar", key=f"fin_cfg_bed_{n}_{chave}"):
            clicado = "editar"
        if visivel is not None and st.button(
            "", icon=":material/visibility_off:" if visivel else ":material/visibility:",
            help="Ocultar do formulário" if visivel else "Mostrar no formulário", key=f"fin_cfg_bvis_{n}_{chave}",
        ):
            clicado = "visivel"
        if excluir and st.button("", icon=":material/delete:", help="Excluir", key=f"fin_cfg_bdel_{n}_{chave}"):
            clicado = "excluir"
    return clicado


def _linha_item(cfg, prefixo, item_id, html, **botoes):
    with st.container(horizontal=True, vertical_alignment="center", gap="small",
                      key=f"fin_cfg_lin_{prefixo}_{cfg['nonce']}_{item_id}"):
        comum.md(html, width="stretch")
        return _botoes_item(cfg, f"{prefixo}{item_id}", **botoes)


def _salvar_cancelar(cfg, sufixo):
    cancelar, salvar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key=f"fin_cfg_fno_{sufixo}"):
        _mudar(cfg)
    return salvar.button("Salvar", type="primary", width="stretch", key=f"fin_cfg_fsim_{sufixo}")


def _form_categoria(cfg, tipo, categoria=None):
    sufixo = f"{cfg['nonce']}_{categoria['id'] if categoria else 'nova_' + tipo}"
    with st.container(key=f"fin_cfg_form_{sufixo}"):
        col_nome, col_cor = st.columns([5, 1], vertical_alignment="bottom")
        nome = col_nome.text_input(
            "Nome da categoria", value=categoria["nome"] if categoria else "", max_chars=NOME_MAX,
            key=f"fin_cfg_in_nome_{sufixo}",
        ).strip()
        cor = col_cor.color_picker(
            "Cor", value=cor_valida(categoria["cor"]) if categoria else COR_PADRAO, key=f"fin_cfg_in_cor_{sufixo}",
        )
        if not _salvar_cancelar(cfg, sufixo):
            return
        if not nome:
            st.error("Dê um nome à categoria.")
            return
        try:
            if categoria:
                repo.atualizar_categoria(categoria["id"], nome, cor_valida(cor))
            else:
                repo.criar_categoria(tipo, nome, cor_valida(cor))
        except repo.NomeDuplicado:
            st.error(f"Já existe uma categoria de {tipo} chamada “{comum.texto_markdown(nome)}” "
                     "(maiúsculas e acentos não contam).")
            return
        _mudar(cfg, aviso="Categoria salva." if categoria else f"Categoria “{nome}” criada.")


def _confirmar_exclusao_categoria(cfg, c, nome_outros):
    em_uso = c["em_uso"]
    texto = ("Nenhum lançamento usa esta categoria." if em_uso == 0 else
             f"1 lançamento irá para {nome_outros}." if em_uso == 1 else
             f"{em_uso} lançamentos irão para {nome_outros}.")

    def excluir():
        movidos = repo.excluir_categoria(c["id"])
        if not movidos:
            return "Categoria excluída."
        return f"Categoria excluída. {_uso(movidos)} movido{'s' if movidos > 1 else ''} para {nome_outros}."

    _confirmacao(cfg, f"c{c['id']}", c["nome"], texto, excluir)


def _item_categoria(cfg, c, tipo, nome_outros):
    modo = cfg["modo"]
    if modo == ("cat_editar", c["id"]):
        _form_categoria(cfg, tipo, c)
        return
    cadeado = comum.icone("lock", "fin-cfg-cadeado") if c["protegida"] else ""
    dica = f' title="{_DICA_OUTROS}"' if c["protegida"] else ""
    clicado = _linha_item(
        cfg, "c", c["id"],
        f'<div class="fin-cfg-item"{dica}>'
        f'<span class="fin-cfg-ponto" style="--cor:{cor_valida(c["cor"])}"></span>'
        f'<span class="fin-cfg-nome">{escape(c["nome"])}</span>{cadeado}'
        f'<span class="fin-cfg-uso">{_uso(c["em_uso"])}</span></div>',
        excluir=not c["protegida"],
    )
    if clicado == "editar":
        _mudar(cfg, ("cat_editar", c["id"]))
    if clicado == "excluir":
        _mudar(cfg, ("cat_excluir", c["id"]))
    if modo == ("cat_excluir", c["id"]):
        _confirmar_exclusao_categoria(cfg, c, nome_outros)


def _secao_categorias(cfg):
    n = cfg["nonce"]
    tipo = comum.escolha(TIPOS_CATEGORIA, f"fin_cfg_tipo_{n}", cfg["tipo"], "Tipo de categoria")
    if tipo != cfg["tipo"]:
        cfg["tipo"], cfg["modo"] = tipo, None
    categorias = repo.listar_categorias(tipo)
    outros = next((c for c in categorias if c["protegida"]), None)
    nome_outros = outros["nome"] if outros else "Outros"

    for c in categorias:
        _item_categoria(cfg, c, tipo, nome_outros)

    if not categorias:
        comum.vazio("Nenhuma categoria ainda.")
    if cfg["modo"] == "cat_nova":
        _form_categoria(cfg, tipo)
    elif st.button("Adicionar categoria", icon=":material/add:", width="stretch", key=f"fin_cfg_add_c_{n}"):
        _mudar(cfg, "cat_nova")


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
            "Cor", value=cor_valida(banco["cor"]) if banco else COR_PADRAO, key=f"fin_cfg_in_bcor_{sufixo}",
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
                repo.atualizar_banco(banco["id"], nome, sigla, cor_valida(cor))
            else:
                repo.criar_banco(nome, sigla, cor_valida(cor))
        except repo.NomeDuplicado:
            st.error(f"Já existe um banco chamado “{comum.texto_markdown(nome)}” (maiúsculas e acentos não contam).")
            return
        _mudar(cfg, aviso="Banco salvo." if banco else f"Banco “{nome}” adicionado.")


def _confirmar_exclusao_banco(cfg, b):
    em_uso = b["em_uso"]
    texto = ("Nenhum lançamento usa este banco." if em_uso == 0 else
             "1 lançamento ficará sem banco." if em_uso == 1 else
             f"{em_uso} lançamentos ficarão sem banco.")
    if b["ativo"]:
        texto += " Para tirar só do formulário, oculte o banco."

    def excluir():
        afetados = repo.excluir_banco(b["id"])
        return f"Banco excluído. {_uso(afetados).capitalize()} ficou sem banco." if afetados == 1 else (
            f"Banco excluído. {afetados} lançamentos ficaram sem banco." if afetados else "Banco excluído.")

    _confirmacao(cfg, f"b{b['id']}", b["nome"], texto, excluir)


def _item_banco(cfg, b):
    modo = cfg["modo"]
    if modo == ("banco_editar", b["id"]):
        _form_banco(cfg, b)
        return
    oculto = '' if b["ativo"] else '<span class="fin-selo">Oculto</span>'
    clicado = _linha_item(
        cfg, "b", b["id"],
        f'<div class="fin-cfg-item{"" if b["ativo"] else " inativo"}">'
        f'{comum.selo_banco(b["sigla"], b["nome"], b["cor"])}{oculto}'
        f'<span class="fin-cfg-uso">{_uso(b["em_uso"])}</span></div>',
        visivel=bool(b["ativo"]),
    )
    if clicado == "editar":
        _mudar(cfg, ("banco_editar", b["id"]))
    if clicado == "visivel":
        repo.definir_banco_ativo(b["id"], not b["ativo"])
        _mudar(cfg, aviso=f"{b['nome']} {'oculto do formulário' if b['ativo'] else 'de volta ao formulário'}.")
    if clicado == "excluir":
        _mudar(cfg, ("banco_excluir", b["id"]))
    if modo == ("banco_excluir", b["id"]):
        _confirmar_exclusao_banco(cfg, b)


def _secao_bancos(cfg):
    n = cfg["nonce"]
    st.caption("Banco oculto some do formulário de lançamento; os lançamentos antigos continuam mostrando o banco.")
    bancos = repo.listar_bancos(incluir_ocultos=True)
    for b in bancos:
        _item_banco(cfg, b)

    if not bancos:
        comum.vazio("Nenhum banco ainda.")
    if cfg["modo"] == "banco_novo":
        _form_banco(cfg)
    elif st.button("Adicionar banco", icon=":material/add:", width="stretch", key=f"fin_cfg_add_b_{n}"):
        _mudar(cfg, "banco_novo")


PADRAO_MAX = 80
_TIPO_REGRA = {None: "Não mudar", "fixo": "Fixo", "variavel": "Variável"}


def _rotulos_categorias():
    rotulos = {}
    for tipo, sufixo in (("gasto", ""), ("entrada", " · entrada")):
        for c in repo.listar_categorias(tipo):
            rotulos[c["id"]] = c["nome"] + sufixo
    return rotulos


def _form_regra(cfg, regra=None):
    sufixo = f"{cfg['nonce']}_r{regra['id'] if regra else 'novo'}"
    rotulos = _rotulos_categorias()
    ids = [None, *rotulos]
    with st.container(key=f"fin_cfg_form_{sufixo}"):
        padrao = st.text_input(
            "Quando a descrição contiver", value=regra["padrao"] if regra else "", max_chars=PADRAO_MAX,
            placeholder="Ex.: netflix", key=f"fin_cfg_in_rpad_{sufixo}",
            help="Não diferencia maiúsculas nem acentos. Vale para a descrição que vem no extrato.",
        ).strip()
        col_categoria, col_tipo = st.columns(2)
        categoria_id = col_categoria.selectbox(
            "Categoria", ids, format_func=lambda i: "Não mudar" if i is None else rotulos[i],
            index=ids.index(regra["categoria_id"]) if regra and regra["categoria_id"] in ids else 0,
            key=f"fin_cfg_in_rcat_{sufixo}", help="Categorias de entrada só valem para entradas.",
        )
        tipo = col_tipo.selectbox(
            "Tipo", list(_TIPO_REGRA), format_func=_TIPO_REGRA.get,
            index=list(_TIPO_REGRA).index(regra["tipo"]) if regra else 0,
            key=f"fin_cfg_in_rtipo_{sufixo}", help="Fixo ou variável só vale para saídas.",
        )
        ignorar = st.checkbox("Ignorar na importação (essas linhas vêm desmarcadas)",
                              value=bool(regra["ignorar"]) if regra else False, key=f"fin_cfg_in_rign_{sufixo}")
        if not _salvar_cancelar(cfg, sufixo):
            return
        norma = normalizar(padrao)
        if not norma:
            st.error("Escreva o texto que a descrição deve conter.")
            return
        if len(norma) < 2:
            st.error("Use pelo menos 2 letras, senão a regra pegaria quase todas as linhas.")
            return
        if categoria_id is None and tipo is None and not ignorar:
            st.error("Escolha uma categoria, um tipo ou marque “Ignorar”.")
            return
        try:
            if regra:
                repo.atualizar_regra(regra["id"], padrao, categoria_id, tipo, ignorar)
            else:
                repo.criar_regra(padrao, categoria_id, tipo, ignorar)
        except repo.NomeDuplicado:
            st.error("Já existe uma regra com esse texto (maiúsculas e acentos não contam).")
            return
        _mudar(cfg, aviso="Regra salva." if regra else "Regra adicionada.")


def _acao_regra(r):
    partes = []
    if r["ignorar"]:
        partes.append("Ignorar")
    if r["categoria_nome"]:
        partes.append(escape(r["categoria_nome"]))
    if r["tipo"]:
        partes.append(comum.TIPO_ROTULO[r["tipo"]])
    return " · ".join(partes) or "Sem efeito"


def _secao_regras(cfg):
    n = cfg["nonce"]
    st.caption("Na importação, quando a descrição de uma linha contém o texto da regra, a categoria, o tipo ou o "
               "“ignorar” dela são aplicados. Você cria aqui ou marcando “Lembrar” na revisão da importação.")
    regras = repo.listar_regras()
    for r in regras:
        if cfg["modo"] == ("regra_editar", r["id"]):
            _form_regra(cfg, r)
            continue
        clicado = _linha_item(
            cfg, "r", r["id"],
            f'<div class="fin-cfg-item"><span class="fin-cfg-nome">{escape(r["padrao"])}</span>'
            f'<span class="fin-cfg-uso">{_acao_regra(r)}</span></div>',
        )
        if clicado == "editar":
            _mudar(cfg, ("regra_editar", r["id"]))
        if clicado == "excluir":
            _mudar(cfg, ("regra_excluir", r["id"]))
        if cfg["modo"] == ("regra_excluir", r["id"]):
            def excluir(regra_id=r["id"]):
                repo.excluir_regra(regra_id)
                return "Regra excluída."

            _confirmacao(cfg, f"r{r['id']}", r["padrao"], "Ela deixa de ser aplicada nas próximas importações.",
                         excluir)
    if not regras and cfg["modo"] != "regra_nova":
        comum.vazio("Nenhuma regra ainda.")
    if cfg["modo"] == "regra_nova":
        _form_regra(cfg)
    elif st.button("Adicionar regra", icon=":material/add:", width="stretch", key=f"fin_cfg_add_r_{n}"):
        _mudar(cfg, "regra_nova")


def _secao_geral(cfg):
    _bloco_saldo(cfg)
    _bloco_nome(cfg)


def _bloco_nome(cfg):
    n = cfg["nonce"]
    # A versão muda a cada gravação, e o campo volta com o valor que está no banco.
    versao = cfg.setdefault("nome_versao", 0)
    secao("badge", "Seu nome")
    st.caption("Usado na importação para reconhecer transferências entre as suas contas: o Pix que cita este nome "
               "vem desmarcado na revisão, para não contar como renda.")
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small", key=f"fin_cfg_nome_{n}"):
        nome = st.text_input(
            "Nome completo, como aparece nos extratos", value=repo.obter_meu_nome(), max_chars=repo.NOME_MAX,
            key=f"fin_cfg_in_nome_{n}_{versao}", width="stretch",
        )
        salvar = st.button("Salvar", type="primary", key=f"fin_cfg_nome_ok_{n}")
    if salvar:
        repo.definir_meu_nome(nome)
        cfg["nome_versao"] = versao + 1
        _mudar(cfg, aviso="Seu nome salvo." if nome.strip() else "Seu nome removido.")


def _bloco_saldo(cfg):
    n = cfg["nonce"]
    saldo = repo.obter_saldo_inicial()
    # A versão muda a cada gravação, e o campo volta com o valor que está no banco.
    versao = cfg.setdefault("saldo_versao", 0)
    secao("account_balance", "Saldo inicial")
    st.caption("Quanto você tinha antes do primeiro lançamento: é o ponto de partida do fluxo de caixa. "
               "Pode ser negativo (ex.: começou devendo).")
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small", key=f"fin_cfg_saldo_{n}"):
        numero = st.number_input(
            "Saldo inicial (R$)", value=float(saldo), min_value=-float(VALOR_MAX),
            max_value=float(VALOR_MAX), step=0.01, format="%.2f", key=f"fin_cfg_in_saldo_{n}_{versao}",
            width="stretch",
        )
        salvar = st.button("Salvar", type="primary", key=f"fin_cfg_saldo_ok_{n}")
    if salvar:
        valor = calc.para_decimal(numero)
        if abs(valor) > VALOR_MAX:
            st.error("Valor alto demais.")
            return
        repo.definir_saldo_inicial(valor)
        cfg["saldo_versao"] = versao + 1
        _mudar(cfg, aviso=f"Saldo inicial salvo: {fmt_brl(valor)}.")


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
        {"categorias": _secao_categorias, "bancos": _secao_bancos, "regras": _secao_regras,
         "geral": _secao_geral}[secao](cfg)
    st.html('<div class="dlg-rodape-linha"></div>')
    if st.button("Fechar", width="stretch", key=f"fin_cfg_fechar_{n}"):
        st.rerun()
