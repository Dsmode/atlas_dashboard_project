"""Triagem automática dos e-mails novos, a cada sincronização agendada (ou manual).

Cada card tem um modo: **sugerir** (padrão: só entra no relatório, nada muda no Gmail), **marcar** (põe o marcador
ATLAS/<card>) ou **quarentena** (marca e tira da caixa de entrada, em ATLAS/Quarentena). Nunca vai para a lixeira
sozinho. Só mexe em e-mail novo (chegou depois da última triagem), nunca em protegido e, na quarentena, nunca em
e-mail que você já leu. A primeira execução só marca o ponto de partida, sem agir.

O cliente do Gmail é injetado, então tudo isto roda nos testes com um Gmail de mentira."""
import json
from datetime import UTC, datetime

from . import analise, classificacao, limpeza, repo

SUGERIR, MARCAR, QUARENTENA = "sugerir", "marcar", "quarentena"
MODOS = {SUGERIR: "Só sugerir", MARCAR: "Marcar sozinho", QUARENTENA: "Marcar e arquivar na quarentena"}
MODOS_POR_CARD_FIXO = {
    classificacao.LIXO: (SUGERIR, MARCAR, QUARENTENA),
    classificacao.SUSPEITO: (SUGERIR, MARCAR, QUARENTENA),
    classificacao.REVISAR: (SUGERIR, MARCAR),  # o que o sistema não sabe não some da caixa sozinho
}
FORMATO = "%Y-%m-%d %H:%M:%S"
CHAVE_MARCO = "ultima_triagem_em"


def agora_utc():
    return datetime.now(UTC).replace(tzinfo=None)


def chave_do_card(card_id):
    return f"u{card_id}"


def modos_permitidos(chave):
    return MODOS_POR_CARD_FIXO.get(chave, (SUGERIR, MARCAR, QUARENTENA))


def modo_do_card(modos, chave):
    modo = modos.get(chave, SUGERIR)
    return modo if modo in modos_permitidos(chave) else SUGERIR


def _cards(caixa):
    """(chave, título, marcador, ids) dos cards fixos e dos do usuário."""
    titulos = {classificacao.LIXO: "Lixo", classificacao.SUSPEITO: "Spam e suspeitos",
               classificacao.REVISAR: "Revisar"}
    for codigo in (classificacao.LIXO, classificacao.SUSPEITO, classificacao.REVISAR):
        yield codigo, titulos[codigo], limpeza.NOMES_FIXOS[codigo], analise.ids_do_card_fixo(caixa, codigo)
    for card in caixa["cards"]:
        yield (chave_do_card(card["id"]), card["nome"], limpeza.nome_do_marcador(card["nome"]),
               caixa["membros"][card["id"]])


def _ler_marco():
    texto = repo.obter_config(CHAVE_MARCO)
    try:
        return datetime.strptime(texto, FORMATO) if texto else None
    except ValueError:
        return None


def triar(cliente, origem="manual", agora=None, calcular=analise.calcular):
    """Uma rodada de triagem. Grava a execução (com o relatório) e devolve o resumo."""
    inicio = agora or agora_utc()
    execucao_id = repo.criar_execucao(origem, inicio)
    try:
        resumo = _triar(cliente, inicio, calcular)
    except Exception as erro:
        repo.finalizar_execucao(execucao_id, agora_utc(), "erro", 0, None, str(erro))
        raise
    repo.finalizar_execucao(execucao_id, agora_utc(), "ok", resumo["novos"], json.dumps(resumo, ensure_ascii=False))
    return resumo


def _triar(cliente, inicio, calcular):
    marco = _ler_marco()
    caixa = calcular()
    por_id = {e["id"]: e for e in caixa["emails"]}
    if marco is None:  # primeira vez: só fixa o ponto de partida, para não agir sobre a caixa antiga
        repo.gravar_config(CHAVE_MARCO, inicio.strftime(FORMATO))
        return {"primeira": True, "novos": 0, "cards": []}

    recentes = {i for i, e in por_id.items() if analise.analisavel(e) and e["data_email"] and e["data_email"] > marco}
    modos = repo.obter_modos()
    relatorio = []
    for chave, titulo, marcador, ids in _cards(caixa):
        novos = sorted(i for i in ids if i in recentes)
        modo = modo_do_card(modos, chave)
        marcados = arquivados = 0
        if novos and modo in (MARCAR, QUARENTENA) and limpeza.marcar(cliente, marcador, novos) is not None:
            marcados = len(novos)
        if novos and modo == QUARENTENA:
            seguros = [i for i in novos if not por_id[i]["lido"] and por_id[i]["na_caixa"]
                       and caixa["classificacao"].get(i, ("",))[0] != classificacao.PROTEGIDO]
            if seguros and limpeza.arquivar(cliente, seguros, f"{titulo}, automático") is not None:
                arquivados = len(seguros)
        relatorio.append({"chave": chave, "titulo": titulo, "modo": modo, "novos": len(novos),
                          "marcados": marcados, "arquivados": arquivados})
    repo.gravar_config(CHAVE_MARCO, inicio.strftime(FORMATO))
    return {"primeira": False, "novos": len(recentes), "cards": relatorio}


def descrever(resumo):
    """Uma linha por card para o relatório da tela."""
    if resumo.get("primeira"):
        return ["Primeira execução: o ponto de partida foi marcado. A partir de agora só e-mails novos entram."]
    linhas = []
    for c in resumo["cards"]:
        if not c["novos"]:
            continue
        if c["modo"] == SUGERIR:
            linhas.append(f"{c['titulo']}: {c['novos']} novos (só sugestão)")
        else:
            partes = [f"{c['marcados']} marcados"] + ([f"{c['arquivados']} arquivados"] if c["arquivados"] else [])
            linhas.append(f"{c['titulo']}: {c['novos']} novos, {', '.join(partes)}")
    return linhas or ["Nenhum e-mail novo caiu em um card."]
