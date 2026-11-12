"""Importação dos metadados do Gmail: carga completa (interrompível e retomável) e sincronização incremental
pela history API. O cliente do Gmail entra como argumento, então tudo aqui testa com um cliente de mentira."""
from datetime import datetime

from database.triagem import metadados, repo
from integracoes.gmail.cliente import HistoricoExpirado
from integracoes.gmail.config import sem_segredos
from integracoes.gmail.tentativas import ErroGmail

# Fase 1 lista a caixa sem spam nem lixeira; a fase 2 lista só o spam, que ajuda a achar remetentes ruins.
CONSULTA_CAIXA = "-in:drafts -in:chats"
TAMANHO_BLOCO = 100  # ids por busca de metadados na carga incremental e por página da carga completa


class Interrompida(Exception):
    """O usuário pediu para pausar; o progresso já está gravado e a importação pode ser retomada."""


def _fases():
    return {
        1: {"query": CONSULTA_CAIXA, "marcador": None, "incluir_spam_lixeira": False},
        2: {"query": None, "marcador": "SPAM", "incluir_spam_lixeira": True},
    }


def _gravar_mensagens(cliente, ids, importacao_id):
    """Busca os metadados de `ids` e grava. Devolve (gravados, ids que sumiram do Gmail)."""
    mensagens, ausentes = cliente.obter_metadados(ids)
    ignoradas = {m["id"] for m in mensagens if metadados.ignorada(m)}
    registros = [metadados.registro_de_mensagem(m) for m in mensagens if m["id"] not in ignoradas]
    repo.gravar_emails(registros, importacao_id)
    return len(registros), [*ausentes, *ignoradas]


def _pagina_completa(cliente, importacao, fase):
    config = _fases()[fase]
    try:
        ids, proximo = cliente.listar_ids(page_token=importacao["page_token"], **config)
    except ErroGmail as erro:
        if erro.status != 400 or not importacao["page_token"]:
            raise
        # O token de página venceu: recomeça a fase. O que já foi gravado nesta importação é pulado.
        ids, proximo = cliente.listar_ids(page_token=None, **config)
    prontos = repo.ids_ja_importados(ids, importacao["id"])
    novos = [i for i in ids if i not in prontos]
    if novos:
        _, sumidos = _gravar_mensagens(cliente, novos, importacao["id"])
        repo.remover_emails(sumidos)
    return ids, proximo


def carga_completa(cliente, importacao, *, reconciliar=False, pausar=lambda: False, ao_progredir=None):
    """Lista toda a caixa e grava os metadados. `importacao` é a linha de tri_importacoes (nova ou retomada):
    fase, page_token e processados são gravados a cada página, então parar e voltar continua de onde parou."""
    while importacao["fase"] in _fases():
        ids, proximo = _pagina_completa(cliente, importacao, importacao["fase"])
        campos = {"processados": importacao["processados"] + len(ids), "page_token": proximo}
        if not proximo:
            campos.update(fase=importacao["fase"] + 1, page_token=None)
        repo.atualizar_importacao(importacao["id"], **campos)
        importacao.update(campos)
        if ao_progredir:
            ao_progredir(importacao)
        if pausar():
            raise Interrompida
    if reconciliar:
        repo.remover_nao_vistos(importacao["id"])
    return importacao


def _eventos_do_historico(cliente, inicio):
    """Percorre o history.list e devolve (ids para reler, ids removidos, historyId atual)."""
    afetados, removidos, token, atual = set(), set(), None, inicio
    while True:
        resposta = cliente.historico(inicio, token)
        for evento in resposta.get("history", []):
            for item in evento.get("messagesDeleted", []):
                removidos.add(item["message"]["id"])
            for chave in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                for item in evento.get(chave, []):
                    afetados.add(item["message"]["id"])
        atual = resposta.get("historyId", atual)
        token = resposta.get("nextPageToken")
        if not token:
            return afetados - removidos, removidos, atual


def incremental(cliente, importacao_id, inicio):
    """Aplica o que mudou no Gmail desde `inicio`. Devolve (historyId novo, quantos e-mails foram relidos)."""
    afetados, removidos, atual = _eventos_do_historico(cliente, inicio)
    lista = sorted(afetados)
    for i in range(0, len(lista), TAMANHO_BLOCO):
        _, sumidos = _gravar_mensagens(cliente, lista[i:i + TAMANHO_BLOCO], importacao_id)
        removidos.update(sumidos)
    repo.remover_emails(removidos)
    return atual, len(lista)


def _agora_texto():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sincronizar_incremental(cliente, historico, pid):
    """Devolve o resumo, ou None se o historyId expirou (aí cabe uma carga completa)."""
    importacao_id = repo.criar_importacao("incremental", pid=pid)
    try:
        novo, relidos = incremental(cliente, importacao_id, historico)
    except HistoricoExpirado:
        repo.atualizar_importacao(importacao_id, status="concluida", finalizada_em=datetime.now())
        return None
    except Exception as erro:
        repo.atualizar_importacao(importacao_id, status="erro", mensagem_erro=sem_segredos(erro)[:500])
        raise
    repo.gravar_config("history_id", novo)
    repo.gravar_config("ultima_sincronizacao", _agora_texto())
    repo.atualizar_importacao(importacao_id, status="concluida", finalizada_em=datetime.now(), processados=relidos)
    return {"modo": "incremental", "relidos": relidos}


def sincronizar(cliente, *, pausar=lambda: False, ao_progredir=None, pid=None):
    """Ponto de entrada: decide entre retomar a carga completa, começar uma nova ou sincronizar só o que mudou.
    Devolve um resumo do que aconteceu."""
    perfil = cliente.perfil()
    repo.gravar_config("email_conta", perfil["emailAddress"])
    repo.gravar_marcadores(cliente.listar_marcadores())
    pendente = repo.importacao_pendente()
    historico = repo.obter_config("history_id")

    if not pendente and historico:
        resumo = _sincronizar_incremental(cliente, historico, pid)
        if resumo:
            return resumo

    if pendente:
        importacao = pendente
        repo.atualizar_importacao(importacao["id"], status="rodando", mensagem_erro=None, pid=pid)
        importacao.update(status="rodando", pid=pid)
    else:
        id_ = repo.criar_importacao("completa", perfil.get("messagesTotal", 0), perfil["historyId"], pid)
        importacao = repo.obter_importacao(id_)
    # Com um historyId antigo guardado, a carga é uma ressincronização: o que sumiu do Gmail sai do banco.
    reconciliar = bool(historico)
    try:
        carga_completa(cliente, importacao, reconciliar=reconciliar, pausar=pausar, ao_progredir=ao_progredir)
    except Interrompida:
        repo.atualizar_importacao(importacao["id"], status="interrompida")
        return {"modo": "completa", "interrompida": True, "relidos": 0}
    except Exception as erro:
        repo.atualizar_importacao(importacao["id"], status="erro", mensagem_erro=sem_segredos(erro)[:500])
        raise
    repo.gravar_config("history_id", importacao["history_id_inicial"])
    repo.atualizar_importacao(importacao["id"], status="concluida", finalizada_em=datetime.now())
    # Tudo o que chegou durante a carga fica entre o historyId inicial e o atual.
    novo, relidos = incremental(cliente, importacao["id"], importacao["history_id_inicial"])
    repo.gravar_config("history_id", novo)
    repo.gravar_config("ultima_sincronizacao", _agora_texto())
    return {"modo": "completa", "relidos": relidos}
