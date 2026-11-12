"""Leituras e cálculos da Central de Triagem guardados em cache. O cache vale enquanto a caixa e as listas do
usuário não mudam (a "versão" muda com a sincronização, os protegidos e as palavras ignoradas)."""
import hashlib

import streamlit as st

from database.triagem import classificacao, repo, tfidf


def versao():
    """Muda quando a caixa, os protegidos ou as palavras ignoradas mudam."""
    dados = repo.resumo()
    protegidos = "|".join(sorted(p["valor"] for p in repo.listar_protegidos()))
    ruido = "|".join(repo.listar_ruido())
    assinatura = f"{dados['total']}|{dados['nao_lidos']}|{repo.obter_config('ultima_sincronizacao')}|{protegidos}|{ruido}"
    return hashlib.md5(assinatura.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False, max_entries=3)
def caixa(chave):
    """Todos os e-mails, a classificação de cada um e o resumo dos cards."""
    repo.garantir_protegidos_padrao(classificacao.PROTEGIDOS_PADRAO)
    protegidos = {p["valor"] for p in repo.listar_protegidos()}
    emails = repo.emails_para_classificar()
    resultado = classificacao.classificar(emails, protegidos)
    return {
        "emails": emails, "classificacao": resultado, "resumo": classificacao.resumo_por_card(emails, resultado),
        "protegidos": sorted(protegidos),
    }


@st.cache_data(show_spinner=False, max_entries=6)
def termos(chave, filtro):
    """Termos e grupos de termos dos e-mails do `filtro` ("todos" ou o nome de um card)."""
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
