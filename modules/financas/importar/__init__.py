"""Aba Importar: anexar o extrato (OFX), escolher banco, intervalo e observação, revisar e gravar no Extrato.

O estado da importação em andamento fica em `st.session_state["fin_imp"]`; sem arquivo no seletor, ele é
descartado (o estado dos widgets também some quando o módulo não é desenhado). Só OFX por enquanto.
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
        st.session_state["fin_imp_banco"] = detectado["id"] if detectado else None
        st.session_state["fin_imp_inicio"] = min(datas + ([extrato.inicio] if extrato.inicio else []))
        st.session_state["fin_imp_fim"] = max(datas + ([extrato.fim] if extrato.fim else []))
        st.session_state["fin_imp_obs"] = ""
    return estado


def _processar(arquivo, bancos):
    """Estado da importação para o arquivo atual do seletor (lê só quando o arquivo muda)."""
    if arquivo is None:
        st.session_state.pop(ESTADO, None)
        # o navegador reenvia os valores dos widgets: só atribuir (antes de criá-los) limpa de verdade
        st.session_state.update({"fin_imp_banco": None, "fin_imp_inicio": None, "fin_imp_fim": None,
                                 "fin_imp_obs": ""})
        return None
    estado = st.session_state.get(ESTADO)
    if estado is None or estado["id_arquivo"] != arquivo.file_id:
        estado = st.session_state[ESTADO] = _carregar(arquivo, bancos)
    return estado


# ---------- cartão do arquivo (esquerda) ----------

def _trocar_arquivo():
    """O seletor só se esvazia com uma chave nova: o nonce na chave faz o papel do X (que fica escondido)."""
    st.session_state["fin_imp_nonce"] = st.session_state.get("fin_imp_nonce", 0) + 1


def _botao_trocar():
    st.button("Trocar arquivo", icon=":material/swap_horiz:", on_click=_trocar_arquivo, key="fin_imp_trocar")


def _cartao_arquivo(estado):
    comum.cabecalho_cartao("Arquivo selecionado", "description")
    if estado is None:
        comum.vazio("Nenhum arquivo selecionado.")
        return
    if estado["erro"]:
        st.error(estado["erro"], icon=":material/error:")
        _botao_trocar()
        return
    extrato = estado["extrato"]
    periodo = f"{_data(extrato.inicio)} a {_data(extrato.fim)}" if extrato.inicio and extrato.fim else "—"
    linhas = (
        ("Tipo", _ORIGEM[extrato.origem]),
        ("Período", periodo),
        ("Conteúdo", _plural(len(extrato.transacoes), "lançamento", "lançamentos") + " no arquivo"),
        ("Instituição", escape(extrato.instituicao) or "—"),
        ("Tamanho", _tamanho(estado["tamanho"])),
    )
    grade = "".join(f"<span>{rotulo}</span><b>{valor}</b>" for rotulo, valor in linhas)
    comum.md(f'<div class="fin-imp-arquivo"><div class="fin-imp-arq-nome">{comum.icone("description")}'
             f'<span>{escape(estado["nome"])}</span></div><div class="fin-imp-arq-grade">{grade}</div></div>')
    _botao_trocar()


# ---------- opções (direita) ----------

def _bancos_html(bancos, ativo):
    if not bancos:
        return '<div class="fin-vazio">Nenhum banco ativo nas configurações.</div>'
    selos = "".join(
        f'<span class="fin-imp-banco{" ativo" if b["id"] == ativo else ""}">'
        f'{comum.selo_banco(b["sigla"], b["nome"], b["cor"])}</span>'
        for b in bancos
    )
    return f'<div class="fin-imp-bancos">{selos}</div>'


def _opcoes(estado, bancos):
    """Banco, intervalo e observação. Devolve (estado do botão, assinatura da escolha) para a revisão."""
    pronto = bool(estado and estado["extrato"])
    extrato = estado["extrato"] if pronto else None
    nomes = {b["id"]: b["nome"] for b in bancos}

    comum.cabecalho_cartao("Selecione o banco", "account_balance")
    comum.md(_bancos_html(bancos, st.session_state.get("fin_imp_banco")))
    banco_id = st.selectbox("Banco", list(nomes), format_func=nomes.get, index=None,
                            placeholder="Selecione o banco", disabled=not pronto, label_visibility="collapsed",
                            key="fin_imp_banco")
    if pronto and banco_id is not None:
        detectado = imp.banco_detectado(extrato, bancos)
        if detectado and detectado["id"] != banco_id:
            comum.md(f'<div class="fin-imp-nota">{comum.icone("info")}O arquivo parece ser do '
                     f'<b>{escape(detectado["nome"])}</b>, mas você escolheu <b>{escape(nomes[banco_id])}</b>.</div>')

    comum.cabecalho_cartao("Intervalo de datas", "date_range")
    col_inicio, col_fim = st.columns(2)
    inicio = col_inicio.date_input("Data início", value=None, format="DD/MM/YYYY", disabled=not pronto,
                                   min_value=_DATA_MIN, max_value=_DATA_MAX, key="fin_imp_inicio")
    fim = col_fim.date_input("Data fim", value=None, format="DD/MM/YYYY", disabled=not pronto,
                             min_value=_DATA_MIN, max_value=_DATA_MAX, key="fin_imp_fim")
    comum.cabecalho_cartao("Observação", "edit_note")
    st.text_input("Observação (aparece no histórico)", max_chars=calc.OBSERVACAO_MAX, disabled=not pronto,
                  placeholder="Ex.: Fatura do cartão de crédito", label_visibility="collapsed", key="fin_imp_obs")

    motivo = None
    if pronto:
        if banco_id is None:
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
                st.caption(_plural(n, "lançamento", "lançamentos") + " neste intervalo.")
            if extrato.inicio and extrato.fim and (inicio < extrato.inicio or fim > extrato.fim):
                st.caption(f"O arquivo cobre de {_data(extrato.inicio)} a {_data(extrato.fim)}.")
    if motivo:
        st.caption(motivo)
    clicou = st.button("Importar dados", icon=":material/upload:", type="primary", disabled=not pronto or bool(motivo),
                       width="stretch", key="fin_imp_botao")
    assinatura = (estado["id_arquivo"], banco_id, inicio, fim) if pronto else None
    return clicou, assinatura


# ---------- aba ----------

def _concluir():
    """Depois de gravar: o seletor ganha uma chave nova (volta vazio) e a tela se atualiza."""
    st.session_state.pop(ESTADO, None)
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
        _cartao_arquivo(estado)
    with direita, st.container(key="fin_card_imp_opcoes"):
        clicou, assinatura = _opcoes(estado, bancos)
    if estado and estado["revisao"] and estado["revisao"]["assinatura"] != assinatura:
        estado["revisao"] = None  # mudou arquivo, banco ou intervalo: a revisão não vale mais
    if clicou:
        estado["revisao"] = revisao.construir(estado, assinatura)
    if estado and estado["revisao"]:
        revisao.abrir(estado, _concluir)
    historico.render_historico()
