"""OAuth 2.0 do Gmail. O refresh token mora no Gerenciador de Credenciais do Windows (keyring); o
client_secret.json fica na pasta de dados, fora do repositório. Nada daqui imprime token.

Rodar `python -m integracoes.gmail.autenticacao conectar` abre o navegador, grava o token e deixa o resultado
em ultima_conexao.json (sem segredos) para a tela acompanhar.
"""
import json
import sys
import urllib.parse
import urllib.request

import keyring
from keyring.errors import KeyringError

from integracoes.gmail import config


class NaoConectado(Exception):
    """Falta o client_secret.json ou o usuário ainda não autorizou o ATLAS."""


class AutenticacaoExpirada(Exception):
    """O Google recusou renovar o token (revogado, senha trocada, 6 meses sem uso): é preciso reconectar."""


def ler_token():
    try:
        return keyring.get_password(config.SERVICO_KEYRING, config.USUARIO_KEYRING)
    except KeyringError:
        return None


def gravar_token(refresh_token):
    keyring.set_password(config.SERVICO_KEYRING, config.USUARIO_KEYRING, refresh_token)


def apagar_token():
    try:
        keyring.delete_password(config.SERVICO_KEYRING, config.USUARIO_KEYRING)
    except KeyringError:
        pass


def ler_client_secret():
    """Devolve (client_id, client_secret) do JSON baixado do Google Cloud (tipo "App para computador")."""
    caminho = config.caminho_client_secret()
    if not caminho.exists():
        raise NaoConectado("O arquivo client_secret.json não foi encontrado.")
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        bloco = dados["installed"]
        return bloco["client_id"], bloco["client_secret"]
    except (ValueError, KeyError, TypeError) as erro:
        raise NaoConectado("O client_secret.json não parece ser de um cliente 'App para computador'.") from erro


def validar_client_secret(conteudo):
    """Confere o JSON enviado pela tela antes de gravar. Devolve None se estiver certo, ou a mensagem de erro."""
    try:
        bloco = json.loads(conteudo)["installed"]
        if not (bloco.get("client_id") and bloco.get("client_secret")):
            raise KeyError
    except (ValueError, KeyError, TypeError, AttributeError):
        return "O arquivo não é um client_secret.json de 'App para computador'. Baixe de novo no Google Cloud."
    return None


def gravar_client_secret(conteudo):
    config.pasta_dados().mkdir(parents=True, exist_ok=True)
    config.caminho_client_secret().write_bytes(conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8"))


def credenciais():
    """Credenciais com access token novo, renovado a partir do refresh token guardado."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    refresh = ler_token()
    if not refresh:
        raise NaoConectado("O ATLAS ainda não foi autorizado a acessar o Gmail.")
    client_id, client_secret = ler_client_secret()
    creds = Credentials(
        token=None, refresh_token=refresh, token_uri=config.TOKEN_URI,
        client_id=client_id, client_secret=client_secret, scopes=[config.ESCOPO],
    )
    try:
        creds.refresh(Request())
    except RefreshError as erro:
        raise AutenticacaoExpirada(
            "O Google não renovou a autorização. Reconecte o Gmail na Central de Triagem."
        ) from erro
    return creds


def status():
    """Estado para a tela: precisa do client_secret, de autorização, ou está conectado."""
    return {"client_secret": config.caminho_client_secret().exists(), "conectado": bool(ler_token())}


def conectar(timeout=300):
    """Abre o navegador para autorizar o escopo gmail.modify e grava o refresh token. Devolve o e-mail da conta."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    ler_client_secret()
    fluxo = InstalledAppFlow.from_client_secrets_file(str(config.caminho_client_secret()), [config.ESCOPO])
    creds = fluxo.run_local_server(
        port=0, prompt="consent", access_type="offline", timeout_seconds=timeout,
        authorization_prompt_message="", success_message="ATLAS conectado ao Gmail. Pode fechar esta aba.",
    )
    if not creds.refresh_token:
        raise NaoConectado("O Google não devolveu o token de renovação. Tente conectar de novo.")
    if config.ESCOPO not in (creds.scopes or []):
        raise NaoConectado("A permissão do Gmail não foi concedida.")
    gravar_token(creds.refresh_token)
    servico = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return servico.users().getProfile(userId="me").execute()["emailAddress"]


def desconectar():
    """Revoga o acesso no Google (se der) e apaga o token local."""
    token = ler_token()
    if token:
        try:
            dados = urllib.parse.urlencode({"token": token}).encode()
            urllib.request.urlopen(
                urllib.request.Request("https://oauth2.googleapis.com/revoke", data=dados), timeout=15,
            ).close()
        except OSError:
            pass
    apagar_token()


def _registrar_resultado(**campos):
    config.pasta_dados().mkdir(parents=True, exist_ok=True)
    config.caminho_resultado_conexao().write_text(json.dumps(campos), encoding="utf-8")


def main(argv):
    if argv[:1] != ["conectar"]:
        print("uso: python -m integracoes.gmail.autenticacao conectar")
        return 2
    _registrar_resultado(estado="aguardando")
    try:
        _registrar_resultado(estado="ok", email=conectar())
    except Exception as erro:
        _registrar_resultado(estado="erro", erro=config.sem_segredos(erro)[:300])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
