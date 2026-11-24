"""Cliente fino da Gmail API: só o que a Central de Triagem usa.

Não existe aqui nenhum método de exclusão permanente: o escopo gmail.modify nem permitiria, e o cliente também
não oferece. As ações da Fase 4 usam só marcadores (labels) e batchModify; mover para a lixeira é adicionar o
marcador TRASH, e tirar da lixeira é o contrário.
"""
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from integracoes.gmail import autenticacao
from integracoes.gmail.tentativas import (
    ErroGmail,
    com_tentativas,
    e_transitorio,
    espera,
    status_http,
)

CABECALHOS = (
    "From", "Subject", "Date", "List-Unsubscribe", "List-Unsubscribe-Post", "Authentication-Results",
    "Received-SPF",
)
TIPOS_HISTORICO = ("messageAdded", "messageDeleted", "labelAdded", "labelRemoved")

# A cota do Gmail é de 250 unidades por segundo por usuário e messages.get custa 5, mas na prática um lote grande
# executa tudo ao mesmo tempo e estoura o limite de rajada (429 e 403 rateLimitExceeded em ~8% das mensagens). Por
# isso o lote é pequeno e o ritmo é adaptativo: cai pela metade quando o Gmail reclama e sobe devagar quando não.
TAMANHO_LOTE = 10
MAX_POR_SEGUNDO = 20
MIN_POR_SEGUNDO = 2
TENTATIVAS_LOTE = 8
MAX_IDS_POR_MODIFICACAO = 1000  # limite do batchModify
PAI_DOS_MARCADORES = "ATLAS"


class HistoricoExpirado(Exception):
    """O historyId guardado é antigo demais para o history.list: é preciso uma nova carga completa."""


class ClienteGmail:
    def __init__(self, servico, *, dormir=time.sleep, agora=time.monotonic):
        self._servico = servico
        self._dormir = dormir
        self._agora = agora
        self._ritmo = MAX_POR_SEGUNDO

    @classmethod
    def conectar(cls):
        servico = build("gmail", "v1", credentials=autenticacao.credenciais(), cache_discovery=False)
        return cls(servico)

    def _executar(self, requisicao):
        try:
            return com_tentativas(requisicao.execute, dormir=self._dormir)
        except HttpError as erro:
            raise ErroGmail(f"O Gmail recusou a requisição (HTTP {status_http(erro)}).", status_http(erro)) from erro

    def perfil(self):
        return self._executar(self._servico.users().getProfile(userId="me"))

    def listar_marcadores(self):
        return self._executar(self._servico.users().labels().list(userId="me")).get("labels", [])

    def listar_ids(self, *, marcador=None, query=None, incluir_spam_lixeira=False, page_token=None):
        """Uma página de ids (até 500). Devolve (ids, próximo_token); o token é None na última página."""
        parametros = {"userId": "me", "maxResults": 500, "includeSpamTrash": incluir_spam_lixeira}
        if marcador:
            parametros["labelIds"] = [marcador]
        if query:
            parametros["q"] = query
        if page_token:
            parametros["pageToken"] = page_token
        resposta = self._executar(self._servico.users().messages().list(**parametros))
        return [m["id"] for m in resposta.get("messages", [])], resposta.get("nextPageToken")

    def obter_metadados(self, ids):
        """Metadados de várias mensagens em lotes, respeitando a cota. Devolve (mensagens, ids_que_sumiram)."""
        mensagens, ausentes = [], []
        for i in range(0, len(ids), TAMANHO_LOTE):
            bloco = ids[i:i + TAMANHO_LOTE]
            inicio = self._agora()
            obtidas, sumidas = self._lote_com_reenvio(bloco)
            mensagens.extend(obtidas)
            ausentes.extend(sumidas)
            folga = len(bloco) / self._ritmo - (self._agora() - inicio)
            if folga > 0:
                self._dormir(folga)
        return mensagens, ausentes

    def _lote_com_reenvio(self, bloco):
        pendentes, obtidas, ausentes = list(bloco), [], []
        for tentativa in range(TENTATIVAS_LOTE):
            respostas, falhas = self._executar_lote(pendentes)
            obtidas.extend(respostas)
            pendentes = []
            for id_, erro in falhas.items():
                if status_http(erro) == 404:
                    ausentes.append(id_)
                elif e_transitorio(erro):
                    pendentes.append(id_)
                else:
                    raise ErroGmail(f"O Gmail recusou a leitura (HTTP {status_http(erro)}).", status_http(erro))
            if not pendentes:
                self._ritmo = min(MAX_POR_SEGUNDO, self._ritmo + 1) if tentativa == 0 else self._ritmo
                return obtidas, ausentes
            self._ritmo = max(MIN_POR_SEGUNDO, self._ritmo / 2)
            self._dormir(espera(tentativa, base=2.0))
        raise ErroGmail("O Gmail continuou limitando o ritmo depois de várias tentativas. Tente de novo em instantes.")

    def _executar_lote(self, ids):
        respostas, falhas = [], {}

        def ao_responder(id_, resposta, erro):
            if erro is None:
                respostas.append(resposta)
            else:
                falhas[id_] = erro

        lote = self._servico.new_batch_http_request(callback=ao_responder)
        mensagens = self._servico.users().messages()
        for id_ in ids:
            lote.add(mensagens.get(userId="me", id=id_, format="metadata", metadataHeaders=list(CABECALHOS)),
                     request_id=id_)
        try:
            com_tentativas(lote.execute, dormir=self._dormir)
        except HttpError as erro:
            raise ErroGmail(f"O Gmail recusou o lote (HTTP {status_http(erro)}).", status_http(erro)) from erro
        return respostas, falhas

    def historico(self, inicio, page_token=None):
        """Uma página do history.list desde `inicio`. Levanta HistoricoExpirado se o id for antigo demais."""
        parametros = {
            "userId": "me", "startHistoryId": inicio, "maxResults": 500, "historyTypes": list(TIPOS_HISTORICO),
        }
        if page_token:
            parametros["pageToken"] = page_token
        try:
            return self._executar(self._servico.users().history().list(**parametros))
        except ErroGmail as erro:
            if erro.status == 404:
                raise HistoricoExpirado from erro
            raise

    # ---------- escrita: marcadores e lixeira (nunca exclusão permanente) ----------

    def garantir_marcador(self, nome):
        """Devolve o id do marcador `nome`, criando-o (e o pai "ATLAS") se ainda não existir."""
        existentes = {m["name"]: m["id"] for m in self.listar_marcadores()}
        if nome in existentes:
            return existentes[nome]
        if "/" in nome:
            pai = nome.rsplit("/", 1)[0]
            if pai not in existentes:
                self.garantir_marcador(pai)
        corpo = {"name": nome, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
        return self._executar(self._servico.users().labels().create(userId="me", body=corpo))["id"]

    def alterar_marcadores(self, ids, adicionar=(), remover=()):
        """Acrescenta e tira marcadores de várias mensagens (batchModify, 1.000 por chamada). Devolve quantas."""
        ids = list(dict.fromkeys(ids))
        if not ids or not (adicionar or remover):
            return 0
        for i in range(0, len(ids), MAX_IDS_POR_MODIFICACAO):
            corpo = {"ids": ids[i:i + MAX_IDS_POR_MODIFICACAO], "addLabelIds": list(adicionar),
                     "removeLabelIds": list(remover)}
            self._executar(self._servico.users().messages().batchModify(userId="me", body=corpo))
        return len(ids)

    def mover_para_lixeira(self, ids):
        """Vai para a lixeira do Gmail (que se esvazia sozinha em 30 dias). Sai da caixa de entrada."""
        return self.alterar_marcadores(ids, adicionar=["TRASH"], remover=["INBOX"])

    def tirar_da_lixeira(self, ids, voltar_para_caixa=()):
        """Desfaz `mover_para_lixeira`. `voltar_para_caixa` são os ids que estavam na caixa de entrada."""
        voltar = set(voltar_para_caixa)
        feitos = self.alterar_marcadores([i for i in ids if i in voltar], adicionar=["INBOX"], remover=["TRASH"])
        return feitos + self.alterar_marcadores([i for i in ids if i not in voltar], remover=["TRASH"])
