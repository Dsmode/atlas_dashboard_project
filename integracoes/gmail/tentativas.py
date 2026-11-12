import json
import random
import time

from googleapiclient.errors import HttpError

STATUS_TRANSITORIOS = {429, 500, 502, 503, 504}
MOTIVOS_DE_COTA = {"rateLimitExceeded", "userRateLimitExceeded", "backendError"}


class ErroGmail(Exception):
    """Falha da API que não adianta tentar de novo."""

    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


def _motivos(erro):
    try:
        corpo = json.loads(erro.content.decode("utf-8", "replace"))
        return {e.get("reason") for e in corpo.get("error", {}).get("errors", [])}
    except (ValueError, AttributeError, TypeError):
        return set()


def status_http(erro):
    return getattr(getattr(erro, "resp", None), "status", None)


def e_transitorio(erro):
    """Cota estourada, servidor do Google instável ou rede caída: vale tentar de novo."""
    if isinstance(erro, HttpError):
        status = status_http(erro)
        if status in STATUS_TRANSITORIOS:
            return True
        return status == 403 and bool(_motivos(erro) & MOTIVOS_DE_COTA)
    return isinstance(erro, OSError) or type(erro).__name__ in {"HttpLib2Error", "ServerNotFoundError"}


def espera(tentativa, base=1.0, teto=60.0, aleatorio=random.random):
    """Backoff exponencial com jitter: 1s, 2s, 4s... até o teto."""
    return min(teto, base * 2 ** tentativa) * (0.5 + aleatorio() / 2)


def com_tentativas(funcao, *, maximo=6, base=1.0, teto=60.0, dormir=time.sleep, aleatorio=random.random):
    ultimo = None
    for tentativa in range(maximo):
        try:
            return funcao()
        except Exception as erro:
            if not e_transitorio(erro):
                raise
            ultimo = erro
            if tentativa < maximo - 1:
                dormir(espera(tentativa, base, teto, aleatorio))
    raise ErroGmail(f"O Gmail não respondeu depois de {maximo} tentativas.", status_http(ultimo)) from ultimo
