import os
import re
from pathlib import Path

# Escopo mínimo: ler, marcar e mover para a lixeira. Não permite exclusão permanente.
ESCOPO = "https://www.googleapis.com/auth/gmail.modify"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SERVICO_KEYRING = "ATLAS-Gmail"
USUARIO_KEYRING = "refresh_token"

_SEGREDOS = re.compile(r"(ya29\.[\w.\-]+|1//[\w\-]+|Bearer\s+[\w.\-]+|GOCSPX-[\w\-]+)")


def pasta_dados():
    """Fora do repositório. ATLAS_GMAIL_DIR existe para os testes."""
    base = os.getenv("ATLAS_GMAIL_DIR")
    if base:
        return Path(base)
    return Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "ATLAS" / "gmail"


def caminho_client_secret():
    return pasta_dados() / "client_secret.json"


def caminho_resultado_conexao():
    return pasta_dados() / "ultima_conexao.json"


def sem_segredos(texto):
    """Tira tokens de qualquer texto que vá para log, banco ou tela."""
    return _SEGREDOS.sub("[removido]", str(texto))
