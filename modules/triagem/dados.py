"""Leituras e cálculos da Central de Triagem guardados em cache. O cache vale enquanto a caixa e as listas do
usuário não mudam (a "versão" muda com a sincronização, os protegidos, as palavras ignoradas e que salvam e os cards)."""
import hashlib
import json

import streamlit as st

from database.triagem import classificacao, regras, repo, tfidf


def versao():
    """Muda quando a caixa, os protegidos, as palavras ou os cards mudam."""
    dados = repo.resumo()
    assinatura = json.dumps([
        dados["total"], str(dados["nao_lidos"]), repo.obter_config("ultima_sincronizacao"),
        sorted(p["valor"] for p in repo.listar_protegidos()), repo.listar_ruido(), repo.listar_palavras_salvam(),
        repo.listar_cards(),
    ], sort_keys=True, default=str)
    return hashlib.md5(assinatura.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False, max_entries=3)
def caixa(chave):
    """Todos os e-mails, a classificação de cada um, os cards do usuário e o resumo de todos os cards."""
    repo.garantir_protegidos_padrao(classificacao.PROTEGIDOS_PADRAO)
    repo.garantir_palavras_salvam_padrao(classificacao.PALAVRAS_SALVAM_PADRAO)
    protegidos = {p["valor"] for p in repo.listar_protegidos()}
    emails = repo.emails_para_classificar()
    preparados = {e["id"]: regras.preparar(e) for e in emails if not e["enviado"]}
    cards = repo.listar_cards()
    salvam = [regras.sem_acento(p) for p in repo.listar_palavras_salvam()]
    resultado = classificacao.classificar(
        emails, protegidos, classificacao.ids_que_casam_com_algum(cards, preparados), salvam, preparados)
    membros = classificacao.membros_dos_cards(cards, preparados, resultado)
    return {
        "emails": emails, "preparados": preparados, "classificacao": resultado, "cards": cards, "membros": membros,
        "resumo": classificacao.resumo_por_card(emails, resultado),
        "resumo_cards": {c["id"]: classificacao.resumo_de_ids(emails, membros[c["id"]]) for c in cards},
        "protegidos": sorted(protegidos),
    }


def cards_do_email(caixa_dados, email_id):
    """Nomes dos cards do usuário em que o e-mail está."""
    return [c["nome"] for c in caixa_dados["cards"] if email_id in caixa_dados["membros"][c["id"]]]


@st.cache_data(show_spinner=False, max_entries=6)
def termos(chave, filtro):
    """Termos e grupos de termos dos e-mails do `filtro` ("todos" ou o nome de um card fixo)."""
    dados = caixa(chave)
    selecionados = [
        e for e in dados["emails"]
        if not e["enviado"] and (filtro == "todos" or dados["classificacao"].get(e["id"], (None,))[0] == filtro)
    ]
    textos = [tfidf.texto_do_email(e["assunto"], e["snippet"]) for e in selecionados]
    itens, matriz, indices = tfidf.extrair_termos(textos, ruido=repo.listar_ruido())
    if not itens:
        return {"itens": [], "grupos": [], "total": len(selecionados)}
    donos = tfidf.principais_remetentes(matriz, indices, [e["dominio"] for e in selecionados])
    for item in itens:
        item["remetentes"] = donos.get(item["termo"], [])
    return {"itens": itens, "grupos": tfidf.grupos_sugeridos(matriz, indices), "total": len(selecionados)}


def chave_tabela(nome):
    """Chave de uma tabela com seleção. Ao mudar os dados, `renovar_tabelas()` troca a chave e a seleção antiga
    (que apontaria para outras linhas) deixa de existir."""
    return f"{nome}_{st.session_state.get('tri_geracao_tabelas', 0)}"


def renovar_tabelas():
    st.session_state.tri_geracao_tabelas = st.session_state.get("tri_geracao_tabelas", 0) + 1
