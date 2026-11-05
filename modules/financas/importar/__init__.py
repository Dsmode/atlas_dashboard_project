"""Aba Importar: anexar o extrato (OFX), escolher banco, intervalo e observação, revisar e gravar no Extrato.

O estado da importação em andamento fica em `st.session_state["fin_imp"]`; sem arquivo no seletor, ele é
descartado (o estado dos widgets também some quando o módulo não é desenhado). Só OFX por enquanto.

Tela em dois cartões: à esquerda a origem do arquivo (área de soltar que vira o "arquivo verificado" e os chips de
banco); à direita o intervalo, a observação e o botão Importar, preso na base.
"""
from datetime import date
from html import escape
from pathlib import Path

import streamlit as st

from database import financas_calculos as calc
from database import financas_importacao as imp
from database import financas_repo as repo
from database.ofx_leitor import TAMANHO_MAX, ArquivoInvalido, ler_ofx
from modules.financas import comum
from modules.financas.importar import historico, revisao

ESTADO = revisao.ESTADO
CHIPS_MAX = 6  # com mais bancos que isso, a grade mostra CHIPS_MAX - 1 chips e o "Outros"
_ORIGEM = {"conta": "Extrato de conta", "cartao": "Fatura de cartão"}
_DATA_MIN, _DATA_MAX = date(2000, 1, 1), date(2100, 12, 31)


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _tamanho(n):
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB".replace(".", ",")
    return f"{n / 1024 ** 2:.1f} MB".replace(".", ",")


def _data(d):
    return d.strftime("%d/%m/%Y") if d else "—"


# ---------- leitura do arquivo ----------

def _carregar(arquivo, bancos):
    """Lê o arquivo anexado e devolve o estado da importação; erros ficam em `erro` (já pronto para a tela)."""
    estado = {"id_arquivo": arquivo.file_id, "nome": arquivo.name or "", "tamanho": arquivo.size or 0,
              "extrato": None, "erro": None, "revisao": None}
    sufixo = Path(estado["nome"]).suffix.lower()
    if sufixo in (".csv", ".pdf"):
        estado["erro"] = "Este formato ainda não é suportado. Por enquanto, só arquivos OFX."
    elif sufixo != ".ofx":
        estado["erro"] = "Formato não reconhecido. Envie um arquivo .ofx."
    elif estado["tamanho"] > TAMANHO_MAX:
        estado["erro"] = "O arquivo é grande demais (limite de 10 MB)."
    else:
        try:
            estado["extrato"] = ler_ofx(arquivo.getvalue())
        except ArquivoInvalido as e:
            estado["erro"] = comum.texto_markdown(str(e))  # a mensagem pode citar texto do arquivo
    extrato = estado["extrato"]
    if extrato:
        # banco e datas começam pelo que o arquivo diz (os widgets são criados depois, na coluna ao lado)
        detectado = imp.banco_detectado(extrato, bancos)
        datas = [t.data for t in extrato.transacoes]
        if detectado:  # banco não reconhecido: fica a escolha que o usuário já fez
            st.session_state["fin_imp_banco"] = detectado["id"]
        st.session_state["fin_imp_inicio"] = min(datas + ([extrato.inicio] if extrato.inicio else []))
        st.session_state["fin_imp_fim"] = max(datas + ([extrato.fim] if extrato.fim else []))
        st.session_state["fin_imp_obs"] = ""
    return estado


def _processar(arquivo, bancos):
    """Estado da importação para o arquivo atual do seletor (lê só quando o arquivo muda)."""
    if arquivo is None:
        st.session_state.pop(ESTADO, None)
        # o navegador reenvia os valores dos widgets: só atribuir (antes de criá-los) limpa de verdade;
        # o banco escolhido fica, porque os chips valem também antes de anexar o arquivo
        st.session_state.update({"fin_imp_inicio": None, "fin_imp_fim": None, "fin_imp_obs": ""})
        return None
    estado = st.session_state.get(ESTADO)
    if estado is None or estado["id_arquivo"] != arquivo.file_id:
        estado = st.session_state[ESTADO] = _carregar(arquivo, bancos)
    return estado


# ---------- área do arquivo (esquerda) ----------

def _trocar_arquivo():
    """O seletor só se esvazia com uma chave nova: o nonce na chave faz o papel do X (que fica escondido)."""
    st.session_state["fin_imp_nonce"] = st.session_state.get("fin_imp_nonce", 0) + 1


def _zona_arquivo(estado):
    """Com arquivo, a área tracejada muda de estado: ícone verificado, nome, tamanho e o que o arquivo traz."""
    if estado is None:
        return
    with st.container(key="fin_imp_zona"):
        if estado["erro"]:
            st.error(estado["erro"], icon=":material/error:")
        else:
            extrato = estado["extrato"]
            detalhes = [_ORIGEM[extrato.origem]]
            if extrato.inicio and extrato.fim:
                detalhes.append(f"{_data(extrato.inicio)} a {_data(extrato.fim)}")
            detalhes.append(_plural(len(extrato.transacoes), "lançamento", "lançamentos"))
            nome = estado["nome"]
            comum.md(
                f'<div class="fin-imp-zona-ok"><div class="fin-imp-zona-ico">{comum.icone("task")}'
                f'<i>{comum.icone("check")}</i></div>'
                f'<div class="fin-imp-zona-nome"><b title="{escape(nome, quote=True)}">{escape(nome)}</b>'
                f'<span>({_tamanho(estado["tamanho"])})</span></div>'
                f'<div class="fin-imp-zona-info">{" · ".join(detalhes)}</div></div>'
            )
        st.button("Remover arquivo", icon=":material/delete:", on_click=_trocar_arquivo, key="fin_imp_remover")


# ---------- chips de banco ----------

def _escolher_banco(banco_id):
    st.session_state["fin_imp_banco"] = banco_id


def _banco_ativo(bancos):
    """Banco marcado; se ele foi excluído ou desativado enquanto estava marcado, a escolha some."""
    atual = st.session_state.get("fin_imp_banco")
    if atual not in {b["id"] for b in bancos}:
        atual = st.session_state["fin_imp_banco"] = None
    return atual


def _divisao(bancos, ativo):
    """(chips da grade, bancos que vão para "Outros"); o banco marcado nunca fica escondido."""
    if len(bancos) <= CHIPS_MAX:
        return bancos, []
    visiveis = bancos[:CHIPS_MAX - 1]
    if ativo is not None and all(b["id"] != ativo for b in visiveis):
        visiveis = bancos[:CHIPS_MAX - 2] + [next(b for b in bancos if b["id"] == ativo)]
    return visiveis, [b for b in bancos if b not in visiveis]


def _chip(corpo_html, classe, chave, rotulo, **botao):
    """O visual é HTML (o mesmo selo dos bancos no resto do módulo); um botão invisível por cima recebe o clique."""
    with st.container(key=f"fin_imp_bk_{chave}"):
        comum.md(f'<div class="fin-imp-chip{classe}">{corpo_html}</div>')
        return st.button(rotulo, key=f"fin_imp_bkb_{chave}", **botao)


def _abrir_outros():
    st.session_state["fin_imp_outros"] = True


def _fechar_outros():
    st.session_state["fin_imp_outros"] = False


def _chip_banco(banco, ativo, na_janela=False):
    selo = comum.selo_banco(banco["sigla"], banco["nome"], banco["cor"])
    marca = f'<i class="fin-imp-chk">{comum.icone("check")}</i>' if ativo else ""
    extra = {} if na_janela else {"on_click": _escolher_banco, "args": (banco["id"],)}
    clicou = _chip(selo + marca, " ativo" if ativo else "", banco["id"], banco["nome"], **extra)
    if clicou and na_janela:  # dentro da janela: grava e fecha com um rerun da página toda
        _escolher_banco(banco["id"])
        _fechar_outros()
        st.rerun()


@st.dialog("Outros bancos", on_dismiss=_fechar_outros)
def _dialogo_outros(restantes, ativo):
    with st.container(key="fin_imp_bancos_outros"):
        for banco in restantes:
            _chip_banco(banco, banco["id"] == ativo, na_janela=True)


def _bancos(estado, bancos):
    """Grade de chips de seleção única. Devolve o id do banco marcado (ou None)."""
    comum.cabecalho_cartao("Selecione o banco", "account_balance")
    ativo = _banco_ativo(bancos)
    if not bancos:
        comum.vazio("Nenhum banco ativo nas configurações.")
        return None
    visiveis, restantes = _divisao(bancos, ativo)
    with st.container(key="fin_imp_bancos"):
        for banco in visiveis:
            _chip_banco(banco, banco["id"] == ativo)
        if restantes:
            _chip(f'{comum.icone("more_horiz")}<span>Outros</span>', " outros", "outros", "Outros",
                  on_click=_abrir_outros)
    if restantes and st.session_state.get("fin_imp_outros"):
        _dialogo_outros(restantes, ativo)
    extrato = estado["extrato"] if estado else None
    if extrato and ativo is not None:
        detectado = imp.banco_detectado(extrato, bancos)
        if detectado and detectado["id"] != ativo:
            escolhido = next(b["nome"] for b in bancos if b["id"] == ativo)
            comum.md(f'<div class="fin-imp-nota">{comum.icone("info")}<span>O arquivo parece ser do '
                     f'<b>{escape(detectado["nome"])}</b>, mas você escolheu <b>{escape(escolhido)}</b>.</span></div>')
    return ativo


# ---------- intervalo, observação e botão (direita) ----------

def _opcoes(estado, banco_id):
    """Intervalo, observação e o botão Importar. Devolve (clicou, assinatura) para a revisão."""
    pronto = bool(estado and estado["extrato"])
    extrato = estado["extrato"] if pronto else None

    comum.cabecalho_cartao("Intervalo de datas", "date_range")
    col_inicio, col_fim = st.columns(2)
    inicio = col_inicio.date_input("Data início", value=None, format="DD/MM/YYYY", disabled=not pronto,
                                   min_value=_DATA_MIN, max_value=_DATA_MAX, key="fin_imp_inicio")
    fim = col_fim.date_input("Data fim", value=None, format="DD/MM/YYYY", disabled=not pronto,
                             min_value=_DATA_MIN, max_value=_DATA_MAX, key="fin_imp_fim")
    comum.cabecalho_cartao("Observação", "edit_note")
    st.text_input("Observação (aparece no histórico)", max_chars=calc.OBSERVACAO_MAX, disabled=not pronto,
                  placeholder="Ex.: Fatura do cartão de crédito", label_visibility="collapsed", key="fin_imp_obs")

    avisos, motivo = [], None
    if estado and estado["erro"]:
        motivo = "Remova o arquivo com erro e anexe outro."
    elif not pronto:
        motivo = "Anexe um arquivo OFX" + (" e escolha o banco." if banco_id is None else " para continuar.")
    elif banco_id is None:
        motivo = "Escolha o banco."
    elif not inicio or not fim:
        motivo = "Informe as duas datas."
    elif fim < inicio:
        motivo = "A data final não pode ser anterior à inicial."
    else:
        n = len(imp.recortar(extrato.transacoes, inicio, fim))
        if n == 0:
            motivo = "Nenhum lançamento neste intervalo."
        else:
            avisos.append(_plural(n, "lançamento", "lançamentos") + " neste intervalo.")
        if extrato.inicio and extrato.fim and (inicio < extrato.inicio or fim > extrato.fim):
            avisos.append(f"O arquivo cobre de {_data(extrato.inicio)} a {_data(extrato.fim)}.")
    # o botão fica preso na base do cartão (CSS) e só libera com arquivo, banco e datas válidos
    with st.container(key="fin_imp_cta"):
        for aviso in avisos:
            st.caption(aviso)
        if motivo:
            st.caption(motivo)
        clicou = st.button("Importar dados", icon=":material/upload:", type="primary", disabled=bool(motivo),
                           width="stretch", key="fin_imp_botao")
    assinatura = (estado["id_arquivo"], banco_id, inicio, fim) if pronto else None
    return clicou, assinatura


# ---------- aba ----------

def _concluir():
    """Depois de gravar: o seletor ganha uma chave nova (volta vazio), o banco é desmarcado e a tela se atualiza."""
    st.session_state.pop(ESTADO, None)
    st.session_state["fin_imp_banco"] = None
    st.session_state["fin_imp_nonce"] = st.session_state.get("fin_imp_nonce", 0) + 1
    st.rerun()


def render(mes):
    comum.mostrar_aviso()
    bancos = repo.listar_bancos()
    esquerda, direita = st.columns([3, 2], gap="medium")
    with esquerda, st.container(key="fin_card_imp_arquivos"):
        arquivo = st.file_uploader(
            "Arquivo do extrato", type=["ofx", "csv", "pdf"], key=f"fin_imp_arquivo_{st.session_state.get('fin_imp_nonce', 0)}",
            label_visibility="collapsed",
        )
        estado = _processar(arquivo, bancos)
        _zona_arquivo(estado)
        banco_id = _bancos(estado, bancos)
    with direita, st.container(key="fin_card_imp_opcoes"):
        clicou, assinatura = _opcoes(estado, banco_id)
    if estado and estado["revisao"] and estado["revisao"]["assinatura"] != assinatura:
        estado["revisao"] = None  # mudou arquivo, banco ou intervalo: a revisão não vale mais
    if clicou:
        estado["revisao"] = revisao.construir(estado, assinatura)
    if estado and estado["revisao"]:
        revisao.abrir(estado, _concluir)
    historico.render_historico()
