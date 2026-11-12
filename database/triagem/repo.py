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


# ---------- leitura para classificar e analisar ----------

def emails_para_classificar():
    """Uma linha por e-mail, só com o que a classificação usa. `spam` e `enviado` vêm dos marcadores do Gmail."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT e.id, e.remetente_nome, e.remetente_email, e.dominio, e.assunto, e.snippet, e.data_email, e.lido, e.categoria, "
            "e.spf, e.dkim, e.dmarc, (e.list_unsubscribe IS NOT NULL AND e.list_unsubscribe <> '') AS tem_cancelamento, "
            "EXISTS (SELECT 1 FROM tri_email_marcadores m WHERE m.email_id = e.id AND m.marcador_id = 'SPAM') AS spam, "
            "EXISTS (SELECT 1 FROM tri_email_marcadores m WHERE m.email_id = e.id AND m.marcador_id = 'SENT') AS enviado "
            "FROM tri_emails e"
        )
        linhas = cur.fetchall()
    for l in linhas:
        l["lido"], l["tem_cancelamento"] = bool(l["lido"]), bool(l["tem_cancelamento"])
        l["spam"], l["enviado"] = bool(l["spam"]), bool(l["enviado"])
    return linhas


# ---------- palavras ignoradas (ruído) ----------

def listar_ruido():
    with get_cursor() as cur:
        cur.execute("SELECT termo FROM tri_ruido ORDER BY termo")
        return [l["termo"] for l in cur.fetchall()]


def substituir_ruido(termos):
    with get_cursor() as cur:
        cur.execute("DELETE FROM tri_ruido")
        if termos:
            cur.executemany("INSERT IGNORE INTO tri_ruido (termo) VALUES (%s)", [(t[:120],) for t in termos])


def adicionar_ruido(termos):
    if termos:
        with get_cursor() as cur:
            cur.executemany("INSERT IGNORE INTO tri_ruido (termo) VALUES (%s)", [(t[:120],) for t in termos])


# ---------- protegidos ----------

def garantir_protegidos_padrao(padrao):
    """Semeia a lista só na primeira vez; depois o usuário manda (se remover um padrão, ele não volta)."""
    if obter_config("protegidos_semeados"):
        return
    with get_cursor() as cur:
        cur.executemany(
            "INSERT IGNORE INTO tri_protegidos (valor, tipo, origem) VALUES (%s, 'dominio', 'padrao')",
            [(v,) for v in padrao],
        )
    gravar_config("protegidos_semeados", "1")


def listar_protegidos():
    with get_cursor() as cur:
        cur.execute("SELECT valor, tipo, origem FROM tri_protegidos ORDER BY tipo, valor")
        return cur.fetchall()


def adicionar_protegidos(itens):
    """`itens`: pares (tipo, valor)."""
    if itens:
        with get_cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO tri_protegidos (valor, tipo, origem) VALUES (%s, %s, 'usuario')",
                [(valor[:320], tipo) for tipo, valor in itens],
            )


def remover_protegidos(valores):
    if valores:
        with get_cursor() as cur:
            cur.executemany("DELETE FROM tri_protegidos WHERE valor = %s", [(v,) for v in valores])


# ---------- palavras que salvam ----------

def garantir_palavras_salvam_padrao(padrao):
    if obter_config("salvam_semeadas"):
        return
    with get_cursor() as cur:
        cur.executemany("INSERT IGNORE INTO tri_palavras_salvam (termo) VALUES (%s)", [(p,) for p in padrao])
    gravar_config("salvam_semeadas", "1")


def listar_palavras_salvam():
    with get_cursor() as cur:
        cur.execute("SELECT termo FROM tri_palavras_salvam ORDER BY termo")
        return [l["termo"] for l in cur.fetchall()]


def substituir_palavras_salvam(termos):
    with get_cursor() as cur:
        cur.execute("DELETE FROM tri_palavras_salvam")
        if termos:
            cur.executemany("INSERT IGNORE INTO tri_palavras_salvam (termo) VALUES (%s)", [(t[:120],) for t in termos])


# ---------- cards configuráveis ----------

def listar_cards():
    """Cards do usuário com os critérios, na ordem de criação."""
    with get_cursor() as cur:
        cur.execute("SELECT id, nome, cor, entra_no_resumo, ordem FROM tri_cards ORDER BY ordem, id")
        cards = cur.fetchall()
        cur.execute("SELECT id, card_id, operador, campo, valor FROM tri_card_criterios ORDER BY id")
        criterios = cur.fetchall()
    por_card = {c["id"]: [] for c in cards}
    for c in criterios:
        por_card[c["card_id"]].append({"operador": c["operador"], "campo": c["campo"], "valor": c["valor"]})
    for c in cards:
        c["entra_no_resumo"] = bool(c["entra_no_resumo"])
        c["criterios"] = por_card[c["id"]]
    return cards


def salvar_card(card_id, nome, cor, entra_no_resumo, criterios):
    """Cria (card_id None) ou atualiza o card, trocando todos os critérios de uma vez. Devolve o id."""
    with get_cursor() as cur:
        if card_id is None:
            cur.execute("SELECT COALESCE(MAX(ordem), 0) + 1 AS proxima FROM tri_cards")
            proxima = cur.fetchone()["proxima"]
            cur.execute(
                "INSERT INTO tri_cards (nome, cor, entra_no_resumo, ordem) VALUES (%s, %s, %s, %s)",
                (nome[:60], cor, int(bool(entra_no_resumo)), proxima),
            )
            card_id = cur.lastrowid
        else:
            cur.execute("UPDATE tri_cards SET nome = %s, cor = %s, entra_no_resumo = %s WHERE id = %s",
                        (nome[:60], cor, int(bool(entra_no_resumo)), card_id))
            cur.execute("DELETE FROM tri_card_criterios WHERE card_id = %s", (card_id,))
        cur.executemany(
            "INSERT INTO tri_card_criterios (card_id, operador, campo, valor) VALUES (%s, %s, %s, %s)",
            [(card_id, c["operador"], c["campo"], c["valor"][:255]) for c in criterios],
        )
    return card_id


def adicionar_criterio(card_id, operador, campo, valor):
    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM tri_card_criterios WHERE card_id = %s AND operador = %s AND campo = %s AND valor = %s",
            (card_id, operador, campo, valor),
        )
        if not cur.fetchone():
            cur.execute("INSERT INTO tri_card_criterios (card_id, operador, campo, valor) VALUES (%s, %s, %s, %s)",
                        (card_id, operador, campo, valor[:255]))


def excluir_card(card_id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM tri_cards WHERE id = %s", (card_id,))
