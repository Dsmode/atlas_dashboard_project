"""Converte a mensagem do Gmail (formato metadata) no registro de `tri_emails`. Sem banco, sem Streamlit."""
import re
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape

CATEGORIAS = {
    "CATEGORY_PROMOTIONS": "promocoes",
    "CATEGORY_SOCIAL": "social",
    "CATEGORY_UPDATES": "atualizacoes",
    "CATEGORY_FORUMS": "foruns",
    "CATEGORY_PERSONAL": "principal",
}
# Rascunhos e conversas do antigo Hangouts não são alvo de triagem.
MARCADORES_IGNORADOS = {"DRAFT", "CHAT"}

_AUTENTICACAO = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-zA-Z]+)")


def _decodificar(valor):
    """Cabeçalhos com acento chegam como =?UTF-8?B?...?=; se algo vier torto, devolve o texto como está."""
    if not valor:
        return ""
    try:
        return str(make_header(decode_header(valor)))
    except (ValueError, LookupError):
        return valor


def _cabecalhos(mensagem):
    por_nome = {}
    for h in mensagem.get("payload", {}).get("headers", []):
        por_nome.setdefault(h["name"].lower(), []).append(h["value"])
    return por_nome


def _primeiro(cabecalhos, nome):
    valores = cabecalhos.get(nome.lower())
    return valores[0].strip() if valores else None


def _remetente(cabecalhos):
    nome, endereco = parseaddr(_decodificar(_primeiro(cabecalhos, "From")))
    endereco = endereco.strip().lower()
    dominio = endereco.rsplit("@", 1)[1] if "@" in endereco else None
    return nome.strip() or None, endereco or None, dominio


def _data(mensagem, cabecalhos):
    """internalDate (ms desde 1970, UTC) é a data confiável; o cabeçalho Date só entra se faltar."""
    bruto = mensagem.get("internalDate")
    if bruto:
        return datetime.fromtimestamp(int(bruto) / 1000, tz=UTC).replace(tzinfo=None)
    try:
        data = parsedate_to_datetime(_primeiro(cabecalhos, "Date") or "")
    except (TypeError, ValueError):
        return None
    return data.astimezone(UTC).replace(tzinfo=None) if data.tzinfo else data


def _resultado_gmail(cabecalhos):
    """O Gmail escreve o seu próprio Authentication-Results (mx.google.com) no topo; um remetente pode forjar
    outros abaixo, então prefere-se o do Gmail."""
    valores = cabecalhos.get("authentication-results", [])
    for valor in valores:
        if valor.strip().lower().startswith("mx.google.com"):
            return valor
    return valores[0] if valores else None


def _autenticacao(cabecalhos):
    resultado = _resultado_gmail(cabecalhos)
    achados = {}
    for metodo, valor in _AUTENTICACAO.findall(resultado or ""):
        achados.setdefault(metodo.lower(), []).append(valor.lower())
    final = {}
    for metodo in ("spf", "dkim", "dmarc"):
        valores = achados.get(metodo)
        if valores:
            final[metodo] = "pass" if "pass" in valores else valores[0]
    if "spf" not in final:
        recebido = _primeiro(cabecalhos, "Received-SPF")
        if recebido:
            final["spf"] = recebido.split(None, 1)[0].lower()
    return final, (re.sub(r"\s+", " ", resultado).strip() if resultado else None)


def _categoria(marcadores):
    for marcador, nome in CATEGORIAS.items():
        if marcador in marcadores:
            return nome
    return "principal" if "INBOX" in marcadores else None


def ignorada(mensagem):
    return bool(MARCADORES_IGNORADOS & set(mensagem.get("labelIds", [])))


def registro_de_mensagem(mensagem):
    """Dicionário com as colunas de `tri_emails` mais `marcadores` (lista de ids de marcador do Gmail)."""
    cabecalhos = _cabecalhos(mensagem)
    marcadores = list(mensagem.get("labelIds", []))
    nome, endereco, dominio = _remetente(cabecalhos)
    auth, auth_bruto = _autenticacao(cabecalhos)
    return {
        "id": mensagem["id"],
        "thread_id": mensagem.get("threadId", mensagem["id"]),
        "remetente_nome": nome[:255] if nome else None,
        "remetente_email": endereco[:320] if endereco else None,
        "dominio": dominio[:255] if dominio else None,
        "assunto": _decodificar(_primeiro(cabecalhos, "Subject"))[:1000],
        "snippet": unescape(mensagem.get("snippet", ""))[:600],
        "data_email": _data(mensagem, cabecalhos),
        "tamanho": int(mensagem.get("sizeEstimate", 0)),
        "lido": "UNREAD" not in marcadores,
        "categoria": _categoria(marcadores),
        "list_unsubscribe": _primeiro(cabecalhos, "List-Unsubscribe"),
        "list_unsubscribe_post": (_primeiro(cabecalhos, "List-Unsubscribe-Post") or "")[:255] or None,
        "spf": auth.get("spf", "")[:20] or None,
        "dkim": auth.get("dkim", "")[:20] or None,
        "dmarc": auth.get("dmarc", "")[:20] or None,
        "auth_resultado": auth_bruto[:1500] if auth_bruto else None,
        "history_id": mensagem.get("historyId"),
        "marcadores": marcadores,
    }
