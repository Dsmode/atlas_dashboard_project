"""Termos mais característicos dos e-mails (TF-IDF) e grupos de termos que aparecem juntos. Puro: recebe textos e
devolve números, sem banco nem Streamlit."""
import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ARQUIVO_STOPWORDS = Path(__file__).with_name("stopwords.txt")
MIN_EMAILS_POR_TERMO = 5      # termo que aparece em menos e-mails que isso não vale uma regra
MAX_FRACAO_DOS_EMAILS = 0.6   # termo que aparece em mais da metade da caixa não distingue nada
MAX_CANDIDATOS = 4000
_PALAVRA = r"(?u)\b[^\W\d_]{3,}\b"  # só letras, 3 ou mais (ignora números, códigos e pontuação)


def ler_stopwords(caminho=ARQUIVO_STOPWORDS):
    linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    return {l.strip().lower() for l in linhas if l.strip() and not l.lstrip().startswith("#")}


def normalizar_ruido(termos):
    """Palavras ignoradas pelo usuário: minúsculas, sem espaços sobrando, sem repetição."""
    return sorted({" ".join(t.lower().split()) for t in termos if t and t.strip()})


def _contem_ruido(termo, ruido):
    palavras = termo.split()
    return any(r in palavras if " " not in r else r in termo for r in ruido)


def extrair_termos(textos, ruido=(), maximo=150, stopwords=None):
    """Devolve a lista de termos (1 a 3 palavras) mais característicos, do mais forte para o mais fraco.

    Cada item: {"termo", "emails", "pontuacao"}. `emails` é em quantos textos o termo aparece. Palavras de
    `ruido` (uma palavra ou uma expressão) e as stopwords nunca entram."""
    if len(textos) < MIN_EMAILS_POR_TERMO:
        return [], None, None
    ruido = normalizar_ruido(ruido)
    paradas = (ler_stopwords() if stopwords is None else set(stopwords)) | {r for r in ruido if " " not in r}
    base = TfidfVectorizer(
        lowercase=True, token_pattern=_PALAVRA, stop_words=sorted(paradas), ngram_range=(1, 3),
    ).build_analyzer()

    def analisar(texto):  # cada linha é um trecho (assunto, assunto de novo, snippet): termos não cruzam trechos
        return [t for trecho in texto.split("\n") for t in base(trecho)]

    vetorizador = TfidfVectorizer(
        analyzer=analisar, min_df=MIN_EMAILS_POR_TERMO, max_df=MAX_FRACAO_DOS_EMAILS, max_features=MAX_CANDIDATOS,
        sublinear_tf=True, dtype=np.float32,
    )
    try:
        matriz = vetorizador.fit_transform(textos)
    except ValueError:  # vocabulário vazio (tudo era ruído ou raro demais)
        return [], None, None
    nomes = vetorizador.get_feature_names_out()
    pontuacao = np.asarray(matriz.sum(axis=0)).ravel()
    emails = np.asarray((matriz > 0).sum(axis=0)).ravel()

    candidatos = [
        (int(i), nomes[i]) for i in np.argsort(-pontuacao) if not _contem_ruido(nomes[i], ruido)
    ]
    mantidos = _sem_redundancia(candidatos, emails)
    itens = [{"termo": nome, "emails": int(emails[i]), "pontuacao": float(pontuacao[i])}
             for i, nome in mantidos[:maximo]]
    return itens, matriz, {nome: i for i, nome in mantidos[:maximo]}


def _sem_redundancia(candidatos, emails):
    """Tira "oferta" quando "oferta imperdível" aparece em quase os mesmos e-mails (a expressão maior já diz tudo)."""
    maior_cobertura = {}  # parte do termo -> mais e-mails que um termo maior que a contém alcança
    for indice, nome in candidatos:
        palavras = nome.split()
        for tamanho in range(1, len(palavras)):
            for inicio in range(len(palavras) - tamanho + 1):
                parte = " ".join(palavras[inicio:inicio + tamanho])
                maior_cobertura[parte] = max(maior_cobertura.get(parte, 0), emails[indice])
    return [(i, nome) for i, nome in candidatos if emails[i] > maior_cobertura.get(nome, 0) * 1.15 + 1]


def principais_remetentes(matriz, indices, dominios, limite=2):
    """Para cada termo (índice de coluna), os domínios que mais enviam e-mails com ele."""
    coluna_a_coluna = matriz.tocsc()
    resultado = {}
    for termo, i in indices.items():
        linhas = coluna_a_coluna[:, i].nonzero()[0]
        contagem = Counter(dominios[r] for r in linhas if dominios[r])
        resultado[termo] = contagem.most_common(limite)
    return resultado


def grupos_sugeridos(matriz, indices, minimo_emails=20, maximo_grupos=6, jaccard_minimo=0.35, tamanho=3):
    """Agrupa termos que andam juntos nos mesmos e-mails (coocorrência, índice de Jaccard).

    Devolve [{"termos": [...], "emails": n}]: `emails` conta os e-mails que têm pelo menos dois dos termos do
    grupo. Cada termo entra em um grupo só."""
    if matriz is None or not indices:
        return []
    termos = list(indices)
    colunas = matriz.tocsc()[:, [indices[t] for t in termos]]
    presenca = (colunas > 0).astype(np.float32).tocsr()
    cooc = (presenca.T @ presenca).toarray()
    freq = np.diag(cooc).copy()
    uniao = freq[:, None] + freq[None, :] - cooc
    jaccard = np.divide(cooc, uniao, out=np.zeros_like(cooc), where=uniao > 0)

    usados, grupos = set(), []
    for i in np.argsort(-freq):
        if i in usados:
            continue
        membros = [i]
        for j in np.argsort(-jaccard[i]):  # termos que dividem palavras são a mesma expressão deslocada: ficam de fora
            if len(membros) == tamanho or jaccard[i, j] < jaccard_minimo:
                break
            if j not in usados and j != i and not any(set(termos[j].split()) & set(termos[m].split()) for m in membros):
                membros.append(j)
        if len(membros) < 2:
            continue
        # e-mails com pelo menos dois dos termos do grupo
        soma = np.asarray(presenca[:, membros].sum(axis=1)).ravel()
        total = int((soma >= 2).sum())
        if total < minimo_emails:
            continue
        usados.update(membros)
        grupos.append({"termos": [termos[m] for m in membros], "emails": total})
    grupos.sort(key=lambda g: -g["emails"])
    return grupos[:maximo_grupos]


def texto_do_email(assunto, snippet):
    """O que entra na análise de cada e-mail: assunto (duas vezes, pesa mais) e o trecho, um por linha."""
    assunto = re.sub(r"\s+", " ", assunto or "").strip()
    trecho = re.sub(r"\s+", " ", snippet or "").strip()
    return f"{assunto}\n{assunto}\n{trecho}"
