from decimal import Decimal
from html import escape

import streamlit as st

from database.cores import COR_PADRAO, cor_valida
from database.dinheiro import VALOR_MAX
from database.metas import repo
from database.metas.modelo import (
    CATEGORIA_NOME_MAX,
    PRIORIDADES,
    TIPOS_NOME,
    TITULO_MAX,
    UNIDADE_MAX,
)
from database.metas.progresso import validar
from modules.metas.visual import cor_texto, fmt_data
from modules.ui import escolha, script, secao

OBJETIVO_ROTULO = {"aumentar": "Chegar a mais", "reduzir": "Chegar a menos"}
OBJETIVO_AJUDA = {
    ("quantidade", "aumentar"): "Você começa com o Valor Atual e sobe até o Alvo. Ex.: ler 12 livros, treinar 20 vezes.",
    ("quantidade", "reduzir"): "Você começa no Valor de Partida e desce até o Alvo. Ex.: perder peso, de 110 kg para 100 kg.",
    ("valor", "aumentar"): "Você começa com o Valor Atual e sobe até o Alvo. Ex.: juntar R$ 5.000.",
    ("valor", "reduzir"): "Você começa no Valor de Partida e desce até o Alvo. Ex.: baixar uma dívida de R$ 6.000 para R$ 1.000.",
}


def abrir_dialogo(meta=None, tarefas=()):
    """O diálogo trabalha numa cópia em session_state["dlg"] e só grava no banco ao salvar. Como o Streamlit
    reexecuta só a função do diálogo a cada interação, o estado inicial precisa ser montado aqui, antes de abri-lo."""
    nonce = st.session_state.get("dlg_nonce", 0) + 1
    st.session_state.dlg_nonce = nonce
    st.session_state.dlg = {
        "nonce": nonce,
        "meta": meta,
        "categorias": {c["id"] for c in meta["categorias"]} if meta else set(),
        "tipo": meta["tipo_progresso"] if meta else "tarefas",
        "objetivo": meta["objetivo"] if meta else "aumentar",
        "n_tarefas_banco": len(tarefas),
        "cat_modo": None,
        "proximo_uid": len(tarefas),
        "tarefas": [
            {"uid": i, "id": t["id"], "descricao": t["descricao"], "prazo": t["prazo"]}
            for i, t in enumerate(tarefas)
        ],
    }
    _dialogo_meta()


def _editor_tarefas(dlg):
    tarefas = dlg["tarefas"]
    n = dlg["nonce"]
    for t in tarefas:
        with st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key=f"dlg_tarefa_{n}_{t['uid']}"):
            prazo = f'<span class="tarefa-prazo">{fmt_data(t["prazo"])}</span>' if t["prazo"] else ""
            st.markdown(f'<div class="tarefa-linha"><span>{escape(t["descricao"])}</span>{prazo}</div>',
                        unsafe_allow_html=True, width="stretch")
            if st.button("", icon=":material/delete:", help="Excluir tarefa", key=f"dlg_del_{n}_{t['uid']}"):
                dlg["tarefas"] = [x for x in tarefas if x["uid"] != t["uid"]]
                st.rerun(scope="fragment")
    if not tarefas:
        st.caption("Nenhuma tarefa ainda.")

    with st.form(f"dlg_nova_tarefa_{n}_{dlg['proximo_uid']}", border=False):
        with st.container(horizontal=True, vertical_alignment="center", gap=None, key="dlg_nova_tarefa"):
            adicionar = st.form_submit_button("", icon=":material/add:", help="Adicionar tarefa")
            descricao = st.text_input(
                "Nova tarefa", placeholder="Nova tarefa...", label_visibility="collapsed", width="stretch",
            )
            prazo = st.date_input(
                "Prazo da tarefa (opcional)", value=None, format="DD/MM/YYYY", label_visibility="collapsed",
                help="Prazo da tarefa (opcional)", width=170,
            )
        if adicionar and descricao.strip():
            dlg["tarefas"].append(
                {"uid": dlg["proximo_uid"], "id": None, "descricao": descricao.strip(), "prazo": prazo}
            )
            dlg["proximo_uid"] += 1
            dlg["focar_tarefa"] = True
            st.rerun(scope="fragment")

    # Depois de adicionar, o cursor volta ao campo (recriado a cada tarefa) para digitar a próxima.
    if dlg.pop("focar_tarefa", False):
        st.html(script("focar_nova_tarefa"), unsafe_allow_javascript=True)


def _campo_numero(rotulo, chave, quantidade, valor, negativo=False):
    if quantidade:
        return Decimal(int(st.number_input(
            rotulo, value=int(valor or 0), min_value=0, max_value=int(VALOR_MAX), step=1, format="%d", key=chave,
        )))
    numero = st.number_input(
        rotulo, value=float(valor or 0), min_value=-float(VALOR_MAX) if negativo else 0.0, max_value=float(VALOR_MAX),
        step=0.01, format="%.2f", key=chave,
    )
    return Decimal(str(round(numero, 2)))


def _aviso_troca(dlg):
    """Trocar o tipo de uma meta salva reinicia o progresso. O aviso aparece antes de gravar."""
    meta = dlg["meta"]
    if not meta or dlg["tipo"] == meta["tipo_progresso"]:
        return
    if meta["tipo_progresso"] != "tarefas":
        perda = "o valor atual será descartado."
    elif dlg["n_tarefas_banco"] > 1:
        perda = f"as {dlg['n_tarefas_banco']} tarefas serão apagadas."
    elif dlg["n_tarefas_banco"] == 1:
        perda = "a 1 tarefa será apagada."
    else:
        perda = "o progresso atual será descartado."
    st.warning(f"Trocar o tipo reinicia o progresso: {perda} Só vale ao salvar.")


def _secao_progresso(dlg):
    """Devolve None (meta de tarefas) ou o dict `progresso` de `salvar_meta`, ainda sem validar: a validação roda
    ao salvar."""
    meta, n = dlg["meta"], dlg["nonce"]
    secao("trending_up", "Progresso")
    tipo = dlg["tipo"] = escolha(TIPOS_NOME, f"dlg_tipo_{n}", dlg["tipo"], "Tipo de progresso")
    _aviso_troca(dlg)
    if tipo == "tarefas":
        return None
    objetivo = dlg["objetivo"] = escolha(OBJETIVO_ROTULO, f"dlg_objetivo_{n}", dlg["objetivo"], "Objetivo")
    # Sem o escape, os dois "R$" do texto viram fórmula.
    st.caption(OBJETIVO_AJUDA[(tipo, objetivo)].replace("$", "\\$"))
    # Se o tipo mudou, recomeça do zero.
    salvo = meta if meta and meta["tipo_progresso"] == tipo else None
    quantidade = tipo == "quantidade"
    sufixo = f"{n}_{tipo}"
    rotulo_valor = "" if quantidade else " (R$)"

    unidade = None
    if quantidade:
        col_alvo, col_unidade = st.columns(2)
        with col_unidade:
            unidade = st.text_input(
                "Unidade (opcional)", value=(salvo["unidade"] or "") if salvo else "", max_chars=UNIDADE_MAX,
                placeholder="livros, km, treinos...", key=f"dlg_unidade_{n}",
            ).strip() or None
    else:
        col_alvo = st.container()
    with col_alvo:
        alvo = _campo_numero(f"Alvo{rotulo_valor}", f"dlg_alvo_{sufixo}", quantidade, salvo and salvo["valor_alvo"])

    inicial = atual = None
    if objetivo == "reduzir":
        inicial = _campo_numero(
            f"Valor de partida{rotulo_valor}", f"dlg_inicial_{sufixo}", quantidade, salvo and salvo["valor_inicial"],
        )
    if objetivo == "reduzir" and not salvo:
        # Meta nova de redução começa na partida.
        atual = inicial
    else:
        atual = _campo_numero(
            f"Valor atual{rotulo_valor}", f"dlg_atual_{sufixo}", quantidade, salvo and salvo["valor_atual"],
            negativo=not quantidade,
        )
    return {"tipo": tipo, "objetivo": objetivo, "unidade": unidade, "inicial": inicial, "alvo": alvo, "atual": atual}


def _ir_para(dlg, modo=None):
    dlg["cat_modo"] = modo
    st.rerun(scope="fragment")


def _form_categoria(dlg, categoria=None):
    """Criar ou editar categoria: só nome e cor. O catálogo grava na hora."""
    n = dlg["nonce"]
    sufixo = f"{n}_{categoria['id'] if categoria else 'nova'}"
    nome = st.text_input(
        "Nome da categoria", value=categoria["nome"] if categoria else "", max_chars=CATEGORIA_NOME_MAX,
        key=f"cat_nome_{sufixo}",
    )
    cor = st.color_picker(
        "Cor", value=cor_valida(categoria["cor"]) if categoria else COR_PADRAO, key=f"cat_cor_{sufixo}",
    )
    col_cancelar, col_salvar = st.columns(2)
    if col_cancelar.button("Cancelar", width="stretch", key=f"cat_cancel_{sufixo}"):
        _ir_para(dlg)
    if col_salvar.button("Salvar", type="primary", width="stretch", key=f"cat_save_{sufixo}"):
        if not nome.strip():
            st.error("Dê um nome à categoria.")
            return
        try:
            if categoria:
                repo.atualizar_categoria(categoria["id"], nome.strip(), cor)
            else:
                dlg["categorias"].add(repo.criar_categoria(nome.strip(), cor))
        except repo.CategoriaDuplicada:
            st.error("Já existe uma categoria com esse nome.")
            return
        _ir_para(dlg)


def _confirmar_exclusao_categoria(dlg, categoria):
    n = dlg["nonce"]
    st.write(
        f"Excluir **{categoria['nome']}**? Ela será removida de {categoria['em_uso']} meta(s); as metas permanecem."
    )
    col_cancelar, col_excluir = st.columns(2)
    if col_cancelar.button("Cancelar", width="stretch", key=f"cat_xno_{n}"):
        _ir_para(dlg)
    if col_excluir.button("Excluir", type="primary", width="stretch", key=f"cat_xsim_{n}"):
        repo.excluir_categoria(categoria["id"])
        dlg["categorias"].discard(categoria["id"])
        _ir_para(dlg)


def _lista_categorias(dlg, categorias):
    n = dlg["nonce"]
    selecionadas = dlg["categorias"]

    def marcar(categoria_id, chave):
        (selecionadas.add if st.session_state[chave] else selecionadas.discard)(categoria_id)

    if not categorias:
        st.caption("Nenhuma categoria ainda.")
    for c in categorias:
        col_ponto, col_nome, col_editar, col_excluir = st.columns([1, 8, 1, 1], vertical_alignment="center")
        col_ponto.markdown(
            f'<span class="cat-dot" style="background:{cor_valida(c["cor"])}"></span>', unsafe_allow_html=True,
        )
        chave = f"cat_chk_{n}_{c['id']}"
        st.session_state[chave] = c["id"] in selecionadas
        col_nome.checkbox(c["nome"], key=chave, on_change=marcar, args=(c["id"], chave))
        if col_editar.button("", icon=":material/edit:", help="Editar categoria", key=f"cat_ed_{n}_{c['id']}"):
            _ir_para(dlg, ("editar", c["id"]))
        if col_excluir.button("", icon=":material/delete:", help="Excluir categoria", key=f"cat_ex_{n}_{c['id']}"):
            _ir_para(dlg, ("excluir", c["id"]))
    if st.button("Criar nova categoria", icon=":material/add:", width="stretch", key=f"cat_new_{n}"):
        _ir_para(dlg, "nova")


def _seletor_categorias(dlg):
    """Campo de categorias no estilo do Trello: um chip com x por categoria marcada e o botão Adicionar, que
    abre o popover para marcar, criar, editar e excluir. Os checkboxes só atualizam a seleção por callback,
    então ela já está em dia quando os chips são desenhados."""
    n = dlg["nonce"]
    categorias = repo.listar_categorias()
    selecionadas = dlg["categorias"]
    modo = dlg["cat_modo"]
    por_id = {c["id"]: c for c in categorias}

    marcadas = [c for c in categorias if c["id"] in selecionadas]
    st.html("<style>" + "".join(
        f'.st-key-dlg_chip_{n}_{c["id"]} button{{background:{cor_valida(c["cor"])};color:{cor_texto(c["cor"])}}}'
        for c in marcadas
    ) + "</style>")
    campo = st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key="dlg_cat_campo")
    with campo:
        for c in marcadas:
            st.button(
                c["nome"], icon=":material/close:", key=f"dlg_chip_{n}_{c['id']}", help="Remover categoria",
                on_click=selecionadas.discard, args=(c["id"],),
            )
    with campo, st.popover("Adicionar", icon=":material/add:", key="dlg_cat_add"):
        if modo == "nova":
            _form_categoria(dlg)
        elif isinstance(modo, tuple) and modo[1] in por_id:
            acao, categoria_id = modo
            if acao == "editar":
                _form_categoria(dlg, por_id[categoria_id])
            else:
                _confirmar_exclusao_categoria(dlg, por_id[categoria_id])
        else:
            _lista_categorias(dlg, categorias)


@st.dialog("Meta", width="large")
def _dialogo_meta():
    dlg = st.session_state.dlg
    meta = dlg["meta"]
    n = dlg["nonce"]

    secao("edit_note", "Detalhes")
    titulo = st.text_input("Título", value=meta["titulo"] if meta else "", max_chars=TITULO_MAX, key=f"dlg_titulo_{n}")
    descricao = st.text_area("Descrição", value=(meta["descricao"] or "") if meta else "", key=f"dlg_desc_{n}")
    col1, col2 = st.columns(2)
    prioridade = col1.selectbox(
        "Prioridade", list(PRIORIDADES),
        index=list(PRIORIDADES).index(meta["prioridade"]) if meta else 1,
        format_func=PRIORIDADES.get, key=f"dlg_prio_{n}",
    )
    prazo = col2.date_input(
        "Prazo (opcional)", value=meta["prazo"] if meta else None, format="DD/MM/YYYY", key=f"dlg_prazo_{n}",
    )

    secao("label", "Categorias")
    _seletor_categorias(dlg)

    progresso = _secao_progresso(dlg)
    if progresso is None:
        secao("checklist", "Tarefas")
        _editor_tarefas(dlg)

    st.html('<div class="dlg-rodape-linha"></div>')
    cancelar, salvar = st.columns(2)
    if cancelar.button("Cancelar", width="stretch", key=f"dlg_cancelar_{n}"):
        st.rerun()
    if salvar.button("Salvar", type="primary", width="stretch", key=f"dlg_salvar_{n}"):
        if not titulo.strip():
            st.error("O título é obrigatório.")
            return
        erro = progresso and validar(
            progresso["tipo"], progresso["objetivo"], progresso["alvo"], progresso["inicial"], progresso["atual"],
        )
        if erro:
            st.error(erro)
            return
        repo.salvar_meta(
            meta["id"] if meta else None, titulo.strip(), descricao.strip() or None,
            prioridade, prazo, dlg["tarefas"], sorted(dlg["categorias"]), progresso,
        )
        st.rerun()


@st.dialog("Confirmar exclusão")
def _dialogo_excluir(meta_id, nome):
    st.write(f"Excluir **{nome}**? Todas as tarefas dela também serão apagadas.")
    col1, col2 = st.columns(2)
    if col1.button("Cancelar", width="stretch"):
        st.rerun()
    if col2.button("Excluir", type="primary", width="stretch"):
        repo.excluir_meta(meta_id)
        st.rerun()


def pedir_exclusao(meta_id, nome):
    if st.session_state.get("confirmar_exclusao", True):
        _dialogo_excluir(meta_id, nome)
    else:
        repo.excluir_meta(meta_id)
        st.rerun()
