"""Exportar e importar os dados das Metas Pessoais: menu do topo e os diálogos (ver database/metas_io.py)."""
from datetime import date
from html import escape

import streamlit as st

from database import metas_io as io

MANTER_DADOS = "Manter os dados atuais"
APAGAR_DADOS = "Apagar os dados atuais"
MESCLAR = "Mesclar com os dados atuais"
SUBSTITUIR_TUDO = "Apagar os dados atuais e importar"
MANTER_ATUAL = "Manter a atual"
USAR_IMPORTADA = "Usar a importada"


def _secao(icone, titulo):
    st.markdown(
        f'<div class="dlg-sec"><span class="material-icon">{icone}</span>{titulo}</div>', unsafe_allow_html=True,
    )


def _curto(texto, maximo=70):
    texto = str(texto)
    return texto if len(texto) <= maximo else texto[:maximo - 1] + "…"


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _resumo(c):
    return ", ".join([
        _plural(c["metas"], "meta", "metas"), _plural(c["tarefas"], "tarefa", "tarefas"),
        _plural(c["categorias"], "categoria", "categorias"),
    ])


def _nome_arquivo():
    return f"atlas-metas-{date.today():%Y-%m-%d}.json"


def mostrar_aviso():
    """Resultado da última exportação/importação (guardado antes do rerun que fechou o diálogo)."""
    aviso = st.session_state.pop("io_aviso", None)
    if aviso:
        st.toast(aviso, icon=":material/check_circle:")


def menu_dados():
    """Botão discreto ao lado de "Nova meta": um menu com Exportar e Importar."""
    with st.popover("", icon=":material/import_export:", help="Exportar ou importar dados", key="io_menu"):
        if st.button("Exportar", icon=":material/download:", key="io_exportar", width="stretch"):
            _abrir_exportacao()
        if st.button("Importar", icon=":material/upload:", key="io_importar", width="stretch"):
            _abrir_importacao()


# ---------- exportar ----------

def _abrir_exportacao():
    st.session_state.io_exp = {"baixou": False}
    st.session_state.io_exp_depois = MANTER_DADOS
    _dialogo_exportar()


def _marcar_baixou():
    st.session_state.io_exp["baixou"] = True


@st.dialog("Exportar dados", width="medium")
def _dialogo_exportar():
    estado = st.session_state.io_exp
    dados, c = io.exportar_json()
    if not (c["metas"] or c["categorias"]):
        st.info("Não há dados nas Metas Pessoais para exportar.")
        return

    _secao("description", "Arquivo")
    st.write(f"O arquivo terá {_resumo(c)} (metas arquivadas incluídas), em formato JSON.")

    _secao("inventory_2", "Depois de exportar")
    depois = st.radio(
        "Depois de exportar", [MANTER_DADOS, APAGAR_DADOS], key="io_exp_depois", label_visibility="collapsed",
        captions=["Nada muda no sistema.", "Remove metas, tarefas e categorias. Só depois de você baixar o arquivo."],
    )

    st.download_button(
        "Baixar arquivo", dados, file_name=_nome_arquivo(), mime="application/json",
        icon=":material/download:", type="primary", width="stretch", key="io_baixar", on_click=_marcar_baixou,
    )
    if not estado["baixou"]:
        if depois == APAGAR_DADOS:
            st.caption("A opção de apagar aparece depois que você baixar o arquivo.")
        return

    if depois == MANTER_DADOS:
        st.success("Arquivo gerado. Os dados continuam no sistema.")
        if st.button("Fechar", width="stretch", key="io_exp_fechar"):
            st.rerun()
        return

    st.warning(
        f"Confira se o arquivo foi salvo no seu computador. Serão apagados {_resumo(c)}. "
        "Não dá para desfazer."
    )
    cancelar, apagar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key="io_exp_cancelar"):
        st.rerun()
    if apagar.button("Já salvei, apagar tudo", type="primary", width="stretch", key="io_exp_apagar"):
        io.apagar_tudo()
        st.session_state.io_aviso = "Dados exportados e apagados do sistema."
        st.rerun()


# ---------- importar ----------

def _abrir_importacao():
    n = st.session_state.get("io_imp_nonce", 0) + 1
    st.session_state.io_imp_nonce = n
    st.session_state.io_imp = {"nonce": n, "id_arquivo": None, "arquivo": None, "plano": None, "erro": None}
    _dialogo_importar()


def _ler_enviado(estado, enviado):
    """Lê o arquivo enviado uma vez só (o diálogo reexecuta a cada clique) e guarda o resultado."""
    if estado["id_arquivo"] == enviado.file_id:
        return
    estado.update(id_arquivo=enviado.file_id, arquivo=None, plano=None, erro=None)
    try:
        arquivo = io.ler_arquivo(enviado.getvalue())
        atuais, categorias = io.carregar_atuais()
        estado["plano"] = io.planejar_mesclagem(arquivo, atuais, categorias)
        estado["arquivo"] = arquivo
    except io.ArquivoInvalido as ex:
        estado["erro"] = str(ex)


def _definir_todos(n, quantidade, quantidade_cores, valor):
    for i in range(quantidade):
        st.session_state[f"io_dec_{n}_{i}"] = valor
    for j in range(quantidade_cores):
        st.session_state[f"io_cor_{n}_{j}"] = valor


def _item_duplicada(conflito):
    atual = conflito["atual"]
    linhas = "".join(
        f'<div class="io-dif"><span class="io-campo">{escape(campo)}</span>'
        f'<span class="io-antes">{escape(_curto(antes))}</span><span class="io-seta">→</span>'
        f'<span class="io-depois">{escape(_curto(depois))}</span></div>'
        for campo, antes, depois in conflito["diferencas"]
    )
    prazo = atual["prazo"].strftime("%d/%m/%Y") if atual["prazo"] else "sem prazo"
    st.markdown(
        f'<div class="io-item"><div class="io-titulo">{escape(_curto(atual["titulo"], 90))}'
        f'<span class="io-prazo">{prazo}</span></div>{linhas}</div>',
        unsafe_allow_html=True,
    )


def _item_cor(conflito):
    ponto = lambda cor: f'<span class="cat-dot io-ponto" style="background:{io.cor_valida(cor)}"></span>'
    st.markdown(
        f'<div class="io-item"><div class="io-titulo">Categoria {escape(_curto(conflito["nome"], 40))}</div>'
        f'<div class="io-dif"><span class="io-campo">Cor</span>{ponto(conflito["cor_atual"])}'
        f'<span class="io-seta">→</span>{ponto(conflito["cor_importada"])}</div></div>',
        unsafe_allow_html=True,
    )


def _painel_mesclagem(arquivo, plano, n):
    conflitos, cores = plano["conflitos"], plano["categorias_conflito"]
    _secao("fact_check", "O que vai acontecer")
    novas, identicas, repetidas = len(plano["novas"]), plano["identicas"], arquivo["repetidas"]
    cat_novas = len(plano["categorias_novas"])
    linhas = [
        (novas, f"**{_plural(novas, 'meta nova', 'metas novas')}** {'será adicionada' if novas == 1 else 'serão adicionadas'}"),
        (identicas, f"**{_plural(identicas, 'meta', 'metas')}** {'já existe igual e fica como está' if identicas == 1 else 'já existem iguais e ficam como estão'}"),
        (len(conflitos), f"**{_plural(len(conflitos), 'meta duplicada', 'metas duplicadas')}** com diferenças: você escolhe abaixo"),
        (cat_novas, f"**{_plural(cat_novas, 'categoria nova', 'categorias novas')}** {'será criada' if cat_novas == 1 else 'serão criadas'}"),
        (repetidas, f"{_plural(repetidas, 'meta repetida', 'metas repetidas')} dentro do arquivo {'foi ignorada' if repetidas == 1 else 'foram ignoradas'}"),
    ]
    st.markdown("\n".join(f"- {texto}" for n_linha, texto in linhas if n_linha))

    if conflitos or cores:
        _secao("difference", "Duplicadas: qual versão fica?")
        st.caption("Duplicada = mesmo título e mesmo prazo. Por padrão a versão atual é mantida.")
        a, b, _ = st.columns([2, 2, 3])
        a.button("Usar todas as importadas", key=f"io_todas_{n}", width="stretch", on_click=_definir_todos,
                 args=(n, len(conflitos), len(cores), USAR_IMPORTADA))
        b.button("Manter todas as atuais", key=f"io_nenhuma_{n}", width="stretch", on_click=_definir_todos,
                 args=(n, len(conflitos), len(cores), MANTER_ATUAL))
        with st.container(height=min(20 + 150 * len(conflitos) + 105 * len(cores), 380), border=False):
            for i, conflito in enumerate(conflitos):
                _item_duplicada(conflito)
                st.radio(f"Meta duplicada {i + 1}", [MANTER_ATUAL, USAR_IMPORTADA], horizontal=True,
                         key=f"io_dec_{n}_{i}", label_visibility="collapsed")
            for j, conflito in enumerate(cores):
                _item_cor(conflito)
                st.radio(f"Cor da categoria {j + 1}", [MANTER_ATUAL, USAR_IMPORTADA], horizontal=True,
                         key=f"io_cor_{n}_{j}", label_visibility="collapsed")

    vazio = not (plano["novas"] or conflitos or plano["categorias_novas"] or cores)
    if vazio:
        st.info("Nada a importar: tudo o que está no arquivo já existe igual.")
    if st.button("Importar", type="primary", width="stretch", key=f"io_confirmar_{n}", disabled=vazio):
        decisao = lambda chave: st.session_state.get(chave) == USAR_IMPORTADA
        try:
            r = io.aplicar_mesclagem(
                arquivo, plano,
                substituir=[i for i in range(len(conflitos)) if decisao(f"io_dec_{n}_{i}")],
                trocar_cores=[c["nome"] for j, c in enumerate(cores) if decisao(f"io_cor_{n}_{j}")],
            )
        except Exception:
            st.error("Não foi possível importar. Nada foi alterado.")
            return
        st.session_state.io_aviso = (
            f"Importação concluída: {_plural(r['novas'], 'meta nova', 'metas novas')}, "
            f"{_plural(r['substituidas'], 'substituída', 'substituídas')}, "
            f"{r['mantidas'] + r['identicas']} mantida(s)."
        )
        st.rerun()


def _painel_substituicao(arquivo, n):
    metas, categorias = io.carregar_atuais()
    atuais = io.contagens(metas, categorias)
    novos = io.contagens(arquivo["metas"], arquivo["categorias"])
    _secao("warning", "Confirmar")
    st.warning(
        f"Serão apagados **{_resumo(atuais)}** do sistema e entrarão **{_resumo(novos)}** do arquivo. "
        "Não dá para desfazer."
    )
    if atuais["metas"] or atuais["categorias"]:
        st.download_button(
            "Baixar backup dos dados atuais (opcional)", io.exportar_json()[0], file_name=_nome_arquivo(),
            mime="application/json", icon=":material/download:", width="stretch", key=f"io_backup_{n}",
            on_click="ignore",
        )
    if st.button("Apagar tudo e importar", type="primary", width="stretch", key=f"io_confirmar_{n}"):
        try:
            io.substituir_tudo(arquivo)
        except Exception:
            st.error("Não foi possível importar. Nada foi alterado.")
            return
        st.session_state.io_aviso = f"Importação concluída: {_resumo(novos)}. Os dados anteriores foram apagados."
        st.rerun()


@st.dialog("Importar dados", width="large")
def _dialogo_importar():
    estado = st.session_state.io_imp
    n = estado["nonce"]

    _secao("upload_file", "Arquivo")
    enviado = st.file_uploader(
        "Arquivo exportado pelas Metas Pessoais (.json)", type=["json"], key=f"io_arquivo_{n}",
    )
    if enviado is None:
        estado.update(id_arquivo=None, arquivo=None, plano=None, erro=None)
        return
    _ler_enviado(estado, enviado)
    if estado["erro"]:
        st.error(estado["erro"])
        return
    arquivo, plano = estado["arquivo"], estado["plano"]
    st.success(f"Arquivo lido: {_resumo(io.contagens(arquivo['metas'], arquivo['categorias']))}.")

    _secao("tune", "Como importar")
    modo = st.radio(
        "Como importar", [MESCLAR, SUBSTITUIR_TUDO], key=f"io_modo_{n}", label_visibility="collapsed",
        captions=["Mantém o que já existe e junta o arquivo; nas duplicadas você decide.",
                  "Remove tudo o que existe hoje e deixa só o conteúdo do arquivo."],
    )
    if modo == MESCLAR:
        _painel_mesclagem(arquivo, plano, n)
    else:
        _painel_substituicao(arquivo, n)
