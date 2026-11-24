"""Cancelar a inscrição em listas de e-mail pelo cabeçalho List-Unsubscribe.

Só o um clique do RFC 8058 é feito pelo ATLAS: um POST em HTTPS com "List-Unsubscribe=One-Click". Link comum fica
para o usuário abrir à mão. O endereço mailto exigiria enviar um e-mail (permissão de envio do Gmail), que não está ativada.

O endereço vem do remetente, então só vai adiante se for HTTPS, sem usuário e senha na URL, na porta 443 e se o
nome resolver só para endereços públicos (nada de localhost nem rede local). Redirecionamentos não são seguidos."""
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request

UM_CLIQUE, LINK, MAILTO, NENHUM = "um_clique", "link", "mailto", "nenhum"
ROTULOS = {
    UM_CLIQUE: "Um clique (HTTPS)", LINK: "Só link: abrir à mão", MAILTO: "Só e-mail (precisa de permissão de envio)",
    NENHUM: "Sem opção de cancelar",
}
CORPO_UM_CLIQUE = b"List-Unsubscribe=One-Click"
TEMPO_LIMITE = 15
_ENTRADA = re.compile(r"<([^<>]+)>")


def analisar(list_unsubscribe, list_unsubscribe_post=None):
    """Lê o cabeçalho e diz o que dá para fazer. Devolve {"metodo", "https", "http", "mailto"}."""
    entradas = [e.strip() for e in _ENTRADA.findall(list_unsubscribe or "")]
    https = next((e for e in entradas if e.lower().startswith("https://")), None)
    http = next((e for e in entradas if e.lower().startswith("http://")), None)
    mailto = next((e for e in entradas if e.lower().startswith("mailto:")), None)
    um_clique = "list-unsubscribe=one-click" in (list_unsubscribe_post or "").lower()
    if https and um_clique:
        metodo = UM_CLIQUE
    elif https or http:
        metodo = LINK
    elif mailto:
        metodo = MAILTO
    else:
        metodo = NENHUM
    return {"metodo": metodo, "https": https, "http": http, "mailto": mailto}


def dominio_da_url(url):
    return (urllib.parse.urlsplit(url or "").hostname or "").lower()


def url_segura(url, resolver=socket.getaddrinfo):
    """(ok, motivo). Só HTTPS, sem credenciais, porta 443 e destino público."""
    try:
        partes = urllib.parse.urlsplit(url or "")
        porta = partes.port
    except ValueError:
        return False, "endereço inválido"
    if partes.scheme.lower() != "https":
        return False, "não é HTTPS"
    if not partes.hostname:
        return False, "endereço sem domínio"
    if partes.username or partes.password:
        return False, "o endereço traz usuário e senha"
    if porta not in (None, 443):
        return False, "porta diferente de 443"
    try:
        for _, _, _, _, destino in resolver(partes.hostname, 443, type=socket.SOCK_STREAM):
            if not ipaddress.ip_address(destino[0]).is_global:
                return False, "o endereço aponta para a rede local"
    except (OSError, ValueError):
        return False, "o domínio não resolve"
    return True, ""


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # o erro 3xx sobe como HTTPError e não é seguido


def desinscrever(url, abrir=None, resolver=socket.getaddrinfo):
    """Faz o POST de um clique. `abrir` é injetável nos testes. Devolve {"ok", "status", "mensagem"}."""
    seguro, motivo = url_segura(url, resolver)
    if not seguro:
        return {"ok": False, "status": None, "mensagem": f"Não foi feito por segurança: {motivo}."}
    pedido = urllib.request.Request(
        url, data=CORPO_UM_CLIQUE, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "ATLAS-Triagem"})
    abrir = abrir or urllib.request.build_opener(_SemRedirecionar).open
    try:
        with abrir(pedido, timeout=TEMPO_LIMITE) as resposta:
            status = resposta.status
    except urllib.error.HTTPError as erro:
        status = erro.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"ok": False, "status": None, "mensagem": "O servidor não respondeu."}
    if 200 <= status < 300:
        return {"ok": True, "status": status, "mensagem": "Pedido aceito pelo remetente."}
    if 300 <= status < 400:
        return {"ok": False, "status": status,
                "mensagem": "O remetente redirecionou para outra página: abra o link à mão para concluir."}
    return {"ok": False, "status": status, "mensagem": f"O remetente recusou (HTTP {status})."}


def por_remetente(cabecalhos):
    """`cabecalhos`: dicts com remetente_email, list_unsubscribe, list_unsubscribe_post, do mais novo para o mais
    antigo. Devolve {remetente: analisar(...)} com o cabeçalho mais recente de cada um que ofereça algum método."""
    achados = {}
    for c in cabecalhos:
        remetente = (c["remetente_email"] or "").lower()
        if remetente and remetente not in achados:
            achado = analisar(c["list_unsubscribe"], c["list_unsubscribe_post"])
            if achado["metodo"] != NENHUM:
                achados[remetente] = achado
    return achados
