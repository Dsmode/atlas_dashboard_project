from database.connection import get_cursor

_COLUNAS_EMAIL = (
    "id", "thread_id", "remetente_nome", "remetente_email", "dominio", "assunto", "snippet", "data_email",
    "tamanho", "lido", "categoria", "list_unsubscribe", "list_unsubscribe_post", "spf", "dkim", "dmarc",
    "auth_resultado", "history_id",
)
_LOTE_SQL = 500


def _em(cur, ids):
    return ", ".join(["%s"] * len(ids))


# ---------- configuração ----------

def obter_config(chave, padrao=None):
    with get_cursor() as cur:
        cur.execute("SELECT valor FROM tri_config WHERE chave = %s", (chave,))
        linha = cur.fetchone()
    return linha["valor"] if linha else padrao


def gravar_config(chave, valor):
    with get_cursor() as cur:
        if valor is None:
            cur.execute("DELETE FROM tri_config WHERE chave = %s", (chave,))
        else:
            cur.execute(
                "INSERT INTO tri_config (chave, valor) VALUES (%s, %s) ON DUPLICATE KEY UPDATE valor = VALUES(valor)",
                (chave, str(valor)),
            )


# ---------- marcadores do Gmail ----------

def gravar_marcadores(marcadores):
    """`marcadores` vem do labels.list do Gmail: dicts com id, name e type ("system" ou "user")."""
    if not marcadores:
        return
    with get_cursor() as cur:
        cur.executemany(
            "INSERT INTO tri_marcadores (id, nome, tipo) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE nome = VALUES(nome), tipo = VALUES(tipo)",
            [(m["id"], m["name"][:255], "sistema" if m.get("type") == "system" else "usuario") for m in marcadores],
        )


# ---------- e-mails ----------

def gravar_emails(registros, importacao_id):
    """Grava (ou atualiza) os e-mails e substitui os marcadores de cada um, tudo numa transação só. Reexecutar
    com os mesmos registros não duplica nada."""
    if not registros:
        return
    colunas = ", ".join(_COLUNAS_EMAIL + ("importacao_id",))
    valores = ", ".join(["%s"] * (len(_COLUNAS_EMAIL) + 1))
    atualizar = ", ".join(f"{c} = VALUES({c})" for c in _COLUNAS_EMAIL[1:] + ("importacao_id",))
    ids = [r["id"] for r in registros]
    with get_cursor() as cur:
        cur.executemany(
            f"INSERT INTO tri_emails ({colunas}) VALUES ({valores}) ON DUPLICATE KEY UPDATE {atualizar}",
            [tuple(r[c] for c in _COLUNAS_EMAIL) + (importacao_id,) for r in registros],
        )
        cur.execute(f"DELETE FROM tri_email_marcadores WHERE email_id IN ({_em(cur, ids)})", ids)
        pares = [(r["id"], m) for r in registros for m in dict.fromkeys(r["marcadores"])]
        if pares:
            cur.executemany("INSERT INTO tri_email_marcadores (email_id, marcador_id) VALUES (%s, %s)", pares)


def remover_emails(ids):
    ids = list(ids)
    removidos = 0
    for i in range(0, len(ids), _LOTE_SQL):
        bloco = ids[i:i + _LOTE_SQL]
        with get_cursor() as cur:
            cur.execute(f"DELETE FROM tri_emails WHERE id IN ({_em(cur, bloco)})", bloco)
            removidos += cur.rowcount
    return removidos


def ids_ja_importados(ids, importacao_id):
    """Dos ids dados, os que a importação `importacao_id` já gravou: a retomada pula esses."""
    if not ids:
        return set()
    with get_cursor() as cur:
        cur.execute(
            f"SELECT id FROM tri_emails WHERE importacao_id = %s AND id IN ({_em(cur, ids)})",
            [importacao_id, *ids],
        )
        return {linha["id"] for linha in cur.fetchall()}


def remover_nao_vistos(importacao_id):
    """Fecha uma carga completa: o que não apareceu nela sumiu do Gmail. O que está na lixeira fica, porque a
    carga completa não lista a lixeira."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM tri_emails WHERE (importacao_id IS NULL OR importacao_id <> %s) AND id NOT IN "
            "(SELECT email_id FROM tri_email_marcadores WHERE marcador_id = 'TRASH')",
            (importacao_id,),
        )
        return cur.rowcount


def resumo():
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(lido = 0), 0) AS nao_lidos, "
            "COUNT(DISTINCT remetente_email) AS remetentes, MIN(data_email) AS mais_antigo FROM tri_emails"
        )
        return cur.fetchone()


# ---------- importações ----------

def criar_importacao(tipo, total_estimado=0, history_id_inicial=None, pid=None):
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO tri_importacoes (tipo, total_estimado, history_id_inicial, pid) VALUES (%s, %s, %s, %s)",
            (tipo, total_estimado, history_id_inicial, pid),
        )
        return cur.lastrowid


_CAMPOS_IMPORTACAO = {
    "status", "fase", "page_token", "total_estimado", "processados", "history_id_inicial", "pid", "finalizada_em",
    "mensagem_erro",
}


def atualizar_importacao(importacao_id, **campos):
    desconhecidos = set(campos) - _CAMPOS_IMPORTACAO
    if desconhecidos:
        raise ValueError(f"Campos desconhecidos: {sorted(desconhecidos)}")
    if not campos:
        return
    with get_cursor() as cur:
        cur.execute(
            f"UPDATE tri_importacoes SET {', '.join(f'{c} = %s' for c in campos)} WHERE id = %s",
            [*campos.values(), importacao_id],
        )


def obter_importacao(importacao_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tri_importacoes WHERE id = %s", (importacao_id,))
        return cur.fetchone()


def importacao_pendente():
    """Carga completa que não terminou (parou, deu erro ou o processo morreu): é a que se retoma."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tri_importacoes WHERE tipo = 'completa' ORDER BY id DESC LIMIT 1")
        ultima = cur.fetchone()
    return ultima if ultima and ultima["status"] != "concluida" else None


def ultima_importacao():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tri_importacoes ORDER BY id DESC LIMIT 1")
        return cur.fetchone()


# ---------- execução única ----------

def nome_trava():
    """Trava do MySQL (por banco) que o processo de importação segura enquanto roda. Se o processo morrer, o
    servidor solta a trava sozinho, então não sobra "importação rodando" fantasma."""
    from database import connection
    return f"atlas_triagem_{connection.DB_NAME}"


def em_execucao():
    with get_cursor() as cur:
        cur.execute("SELECT IS_FREE_LOCK(%s) AS livre", (nome_trava(),))
        return cur.fetchone()["livre"] == 0
