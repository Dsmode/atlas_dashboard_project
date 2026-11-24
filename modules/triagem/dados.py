"""Leituras e cálculos da Central de Triagem guardados em cache. O cache vale enquanto a caixa e as listas do
usuário não mudam (a "versão" muda com a sincronização, os protegidos, as palavras ignoradas e que salvam e os cards)."""
import hashlib
import json

import streamlit as st

from database.triagem import analise, repo, tfidf


def versao():
    """Muda quando a caixa, os protegidos, as palavras ou os cards mudam."""
    dados = repo.resumo()
    assinatura = json.dumps([
        dados["total"], str(dados["nao_lidos"]), repo.obter_config("ultima_sincronizacao"),
        sorted(p["valor"] for p in repo.listar_protegidos()), repo.listar_ruido(), repo.listar_palavras_salvam(),
        repo.listar_cards(), sorted(b["valor"] for b in repo.listar_bloqueados()), repo.listar_acoes(1),
        sorted(str(d["feita_em"]) for d in repo.listar_desinscricoes().values()),
    ], sort_keys=True, default=str)
    return hashlib.md5(assinatura.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False, max_entries=3)
def caixa(chave):
    return analise.calcular()


def cards_do_email(caixa_dados, email_id):
    """Nomes dos cards do usuário em que o e-mail está."""
    return [c["nome"] for c in caixa_dados["cards"] if email_id in caixa_dados["membros"][c["id"]]]


@st.cache_data(show_spinner=False, max_entries=6)
def termos(chave, filtro):
    """Termos e grupos de termos dos e-mails do `filtro` ("todos" ou o nome de um card fixo)."""
    dados = caixa(chave)
    selecionados = [
        e for e in dados["emails"]
        if analise.analisavel(e) and (filtro == "todos" or dados["classificacao"].get(e["id"], (None,))[0] == filtro)
    ]
    textos = [tfidf.texto_do_email(e["assunto"], e["snippet"]) for e in selecionados]
    itens, matriz, indices = tfidf.extrair_termos(textos, ruido=repo.listar_ruido())
    if not itens:
        return {"itens": [], "grupos": [], "total": len(selecionados)}
    donos = tfidf.principais_remetentes(matriz, indices, [e["dominio"] for e in selecionados])
    for item in itens:
        item["remetentes"] = donos.get(item["termo"], [])
    return {"itens": itens, "grupos": tfidf.grupos_sugeridos(matriz, indices), "total": len(selecionados)}


@st.cache_data(show_spinner=False, max_entries=2)
def cabecalhos_de_lista(chave):
    """Cabeçalhos List-Unsubscribe (do mais novo para o mais antigo): leitura pesada, vale o cache da caixa."""
    return repo.cabecalhos_de_lista()


def chave_tabela(nome):
    """Chave de uma tabela com seleção. Ao mudar os dados, `renovar_tabelas()` troca a chave e a seleção antiga
    (que apontaria para outras linhas) deixa de existir."""
    return f"{nome}_{st.session_state.get('tri_geracao_tabelas', 0)}"


def renovar_tabelas():
    st.session_state.tri_geracao_tabelas = st.session_state.get("tri_geracao_tabelas", 0) + 1
