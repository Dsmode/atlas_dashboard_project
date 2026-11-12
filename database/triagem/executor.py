"""Processo que sincroniza a caixa com o Gmail. A tela o abre em segundo plano e o Agendador do Windows o chama
sozinho: `python -m database.triagem.executor`. O progresso e os erros ficam no banco; o log só tem contagens."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import mysql.connector

from database import connection
from database.triagem import importacao, repo
from integracoes.gmail import config
from integracoes.gmail.autenticacao import AutenticacaoExpirada, NaoConectado
from integracoes.gmail.cliente import ClienteGmail

OK, ERRO, JA_RODANDO, SEM_AUTORIZACAO = 0, 1, 2, 3
log = logging.getLogger("triagem")


def _configurar_log():
    pasta = config.pasta_dados().parent
    pasta.mkdir(parents=True, exist_ok=True)
    manipulador = RotatingFileHandler(pasta / "triagem.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    manipulador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(manipulador)
    log.setLevel(logging.INFO)


def _adquirir_trava():
    """Conexão que segura a trava enquanto o processo viver. Devolve None se outra execução já a tem."""
    conn = mysql.connector.connect(**connection._config())
    cur = conn.cursor()
    cur.execute("SELECT GET_LOCK(%s, 0)", (repo.nome_trava(),))
    if cur.fetchone()[0] == 1:
        return conn
    conn.close()
    return None


def _registrar_erro(tipo, erro):
    from datetime import datetime
    repo.gravar_config("ultimo_erro_tipo", tipo)
    repo.gravar_config("ultimo_erro", config.sem_segredos(erro)[:240])
    repo.gravar_config("ultimo_erro_em", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _limpar_erro():
    for chave in ("ultimo_erro_tipo", "ultimo_erro", "ultimo_erro_em"):
        repo.gravar_config(chave, None)


def executar(criar_cliente=ClienteGmail.conectar):
    connection.init_db()
    trava = _adquirir_trava()
    if trava is None:
        log.info("Já existe uma sincronização em andamento.")
        return JA_RODANDO
    try:
        repo.gravar_config("pedido_pausa", None)
        resumo = importacao.sincronizar(
            criar_cliente(), pid=os.getpid(), pausar=lambda: repo.obter_config("pedido_pausa") == "1",
        )
        _limpar_erro()
        log.info("Sincronização %s: %s", resumo.get("modo"), {k: v for k, v in resumo.items() if k != "modo"})
        return OK
    except (NaoConectado, AutenticacaoExpirada) as erro:
        _registrar_erro("autorizacao", erro)
        log.warning("Autorização necessária: %s", config.sem_segredos(erro))
        return SEM_AUTORIZACAO
    except Exception as erro:
        _registrar_erro("geral", erro)
        log.error("Falha na sincronização: %s", config.sem_segredos(erro))
        return ERRO
    finally:
        trava.close()


def main():
    _configurar_log()
    return executar()


if __name__ == "__main__":
    sys.exit(main())
