"""Ações no Gmail a partir da tela: marcar, arquivar, mover para a lixeira, marcar como golpe, exportar CSV.
Marcar só etiqueta; arquivar e lixeira pedem confirmação com os números exatos. Tudo vai para o histórico."""
import io
from html import escape

import pandas as pd
import streamlit as st

from database.triagem import classificacao as cl
from database.triagem import limpeza, repo
from database.triagem.estado import fmt_int
from integracoes.gmail import autenticacao, config
from integracoes.gmail.cliente import ClienteGmail
from integracoes.gmail.tentativas import ErroGmail

from . import dados

PALAVRA_DE_CONFIRMACAO = "MOVER"


def avisar(texto, tipo="sucesso"):
    st.session_state.tri_aviso = (tipo, texto)


def mostrar_aviso():
    aviso = st.session_state.pop("tri_aviso", None)
    if aviso:
        (st.success if aviso[0] == "sucesso" else st.error)(aviso[1])


def _com_cliente(acao):
    """Roda `acao(cliente)` e transforma as falhas esperadas em um aviso. Devolve o resultado ou None."""
    try:
        return acao(ClienteGmail.conectar())
    except (autenticacao.NaoConectado, autenticacao.AutenticacaoExpirada):
        avisar("O Gmail não está conectado. Reconecte na faixa de cima e tente de novo.", "erro")
    except ErroGmail as erro:
        avisar(f"O Gmail não concluiu a ação: {erro}", "erro")
    except limpeza.ProtegidoNaSelecao:
        avisar("A seleção tem remetentes protegidos e a confirmação extra não foi dada.", "erro")
    except Exception as erro:  # noqa: BLE001  (a tela mostra o motivo em vez de quebrar)
        avisar(f"Algo falhou no meio da ação: {config.sem_segredos(erro)}", "erro")
    return None


def _concluir(acao_id, vazio):
    dados.renovar_tabelas()
    if acao_id is None:
        avisar(vazio)
        return
    acao = repo.obter_acao(acao_id)
    avisar(f"{acao['descricao']}. Dá para desfazer em Histórico.")


def nome_do_marcador(aberto, caixa):
    if aberto in limpeza.NOMES_FIXOS:
        return limpeza.NOMES_FIXOS[aberto]
    return limpeza.nome_do_marcador(next(c["nome"] for c in caixa["cards"] if c["id"] == aberto))


def ids_dos_remetentes(caixa, ids, remetentes):
    alvo = set(remetentes)
    return {e["id"] for e in caixa["emails"] if e["id"] in ids and (e["remetente_email"] or "").lower() in alvo}


def _protegidos_do(caixa, ids):
    return {i for i in ids if caixa["classificacao"].get(i, ("",))[0] == cl.PROTEGIDO}


# ---------- marcar ----------

def marcar_no_gmail(caixa, aberto, ids_card, ids_escolhidos=None):
    """Sem `ids_escolhidos`: sincroniza o marcador com o card inteiro (marca os que entraram, tira dos que saíram).
    Com `ids_escolhidos`: só acrescenta o marcador a esses e-mails."""
    nome = nome_do_marcador(aberto, caixa)
    if ids_escolhidos is not None:
        com, sem = sorted(ids_escolhidos), []
    else:
        com = sorted(ids_card)
        marcador_id = {m["nome"]: m["id"] for m in repo_marcadores()}.get(nome)
        sem = sorted(repo.ids_com_marcador(marcador_id) - set(ids_card)) if marcador_id else []
    acao_id = _com_cliente(lambda cliente: limpeza.marcar(cliente, nome, com, sem))
    if acao_id is not None or st.session_state.get("tri_aviso") is None:
        _concluir(acao_id, f"Nada a fazer: os e-mails já estão marcados com {nome}.")


def repo_marcadores():
    with repo.get_cursor() as cur:
        cur.execute("SELECT id, nome FROM tri_marcadores")
        return cur.fetchall()


# ---------- diálogos de confirmação ----------

@st.dialog("Arquivar na quarentena")
def _dialogo_arquivar(origem, ids, remetentes, na_caixa):
    fora = len(ids) - na_caixa
    st.markdown(
        f"**{fmt_int(len(ids))} e-mails** de **{fmt_int(remetentes)} remetentes** ganham o marcador "
        f"**{limpeza.QUARENTENA}**, sem prazo até você revisar. **{fmt_int(na_caixa)}** saem da caixa de entrada"
        + (f"; os outros **{fmt_int(fora)}** já estão fora dela (por exemplo, na pasta Spam do Gmail) e só ganham o "
           "marcador. Para vê-los no Gmail, busque `in:anywhere label:atlas-quarentena`." if fora else ".")
        + " Nada é apagado.")
    esquerda, direita = st.columns(2)
    if esquerda.button("Cancelar", key="tri_dlg_arq_cancelar", width="stretch"):
        st.rerun()
    if direita.button("Arquivar", key="tri_dlg_arq_ok", type="primary", width="stretch"):
        with st.spinner("Arquivando no Gmail…"):
            acao_id = _com_cliente(lambda cliente: limpeza.arquivar(cliente, sorted(ids), origem))
        _concluir(acao_id, "Nada a arquivar: já estão na quarentena.")
        st.rerun()


@st.dialog("Mover para a lixeira")
def _dialogo_lixeira(origem, plano, protegidos_na_selecao, extra):
    ids = plano["ids"]
    st.markdown(
        f"Vão para a lixeira do Gmail **{fmt_int(len(ids))} e-mails** de **{fmt_int(plano['remetentes'])} "
        f"remetentes** ({escape(origem)}). A lixeira do Gmail se esvazia sozinha em 30 dias; até lá você desfaz em "
        "Histórico.")
    if plano["protegidos_fora"]:
        st.info(f"{fmt_int(plano['protegidos_fora'])} e-mails de remetentes protegidos ficaram de fora.")
    liberado = True
    if extra:
        st.warning("Estes e-mails são de remetentes **protegidos** (bancos, governo, vagas). Confirme que é isso "
                   "mesmo que você quer.")
        entendi = st.checkbox("Entendo que são remetentes protegidos", key="tri_dlg_lix_entendi")
        digitado = st.text_input(f"Digite {PALAVRA_DE_CONFIRMACAO} para confirmar", key="tri_dlg_lix_palavra")
        liberado = entendi and digitado.strip().upper() == PALAVRA_DE_CONFIRMACAO
    esquerda, direita = st.columns(2)
    if esquerda.button("Cancelar", key="tri_dlg_lix_cancelar", width="stretch"):
        st.rerun()
    if direita.button("Mover para a lixeira", key="tri_dlg_lix_ok", type="primary", width="stretch",
                      disabled=not liberado or not ids):
        with st.spinner("Movendo no Gmail…"):
            acao_id = _com_cliente(lambda cliente: limpeza.mover_para_lixeira(
                cliente, ids, origem, protegidos_na_selecao=protegidos_na_selecao, confirmou_protegidos=extra))
        _concluir(acao_id, "Nada a mover: já estão na lixeira.")
        st.rerun()


def pedir_lixeira(caixa, ids, origem, extra=False):
    """Abre a confirmação. Sem `extra`, remetentes protegidos ficam fora; com `extra` (só na seção de protegidos),
    entram, depois da confirmação por escrito."""
    emails = {e["id"]: e for e in caixa["emails"]}
    plano = limpeza.planejar_lixeira(ids, emails, caixa["classificacao"], permitir_protegidos=extra)
    _dialogo_lixeira(origem, plano, _protegidos_do(caixa, plano["ids"]) if extra else set(), extra)


def pedir_arquivar(caixa, ids, origem):
    emails = {e["id"]: e for e in caixa["emails"]}
    plano = limpeza.planejar_lixeira(ids, emails, caixa["classificacao"])
    na_caixa = sum(1 for i in plano["ids"] if emails[i]["na_caixa"])
    _dialogo_arquivar(origem, plano["ids"], plano["remetentes"], na_caixa)


# ---------- golpe ----------

def marcar_como_golpe(linhas, indices, por):
    itens = []
    for i in indices:
        remetente, dominio = linhas[i]["remetente"], linhas[i]["dominio"]
        itens.append(("email", remetente) if por == "email" else ("dominio", dominio))
    itens = [x for x in itens if x[1] and x[1] != "(sem remetente)"]
    repo.adicionar_bloqueados(itens, "Marcado por você como golpe")
    dados.renovar_tabelas()
    avisar(f"{len(itens)} {'remetente bloqueado' if len(itens) == 1 else 'remetentes bloqueados'}. Os e-mails "
           "deles agora aparecem em Spam e suspeitos, antes de qualquer protegido ou regra.")


# ---------- exportar ----------

def csv_do_card(caixa, titulo, ids, motivo_de):
    por_id = {e["id"]: e for e in caixa["emails"]}
    linhas = [por_id[i] for i in sorted(ids, key=lambda i: (por_id[i]["data_email"] is None, por_id[i]["data_email"]),
                                        reverse=True)]
    tabela = pd.DataFrame({
        "card": titulo, "remetente": [e["remetente_email"] for e in linhas], "nome": [e["remetente_nome"] for e in linhas],
        "assunto": [e["assunto"] for e in linhas],
        "data": [e["data_email"].strftime("%Y-%m-%d %H:%M") if e["data_email"] else "" for e in linhas],
        "lido": ["sim" if e["lido"] else "não" for e in linhas], "motivo": [motivo_de(e) for e in linhas],
        "id_gmail": [e["id"] for e in linhas],
    })
    buffer = io.StringIO()
    tabela.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8-sig")  # o BOM faz o Excel abrir os acentos certos
