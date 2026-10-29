from datetime import date, timedelta

from mysql.connector.errors import IntegrityError

from database.connection import get_cursor


def listar_metas():
    """Todas as metas; cada uma traz `categorias` (lista de dicts id/nome/cor, em ordem alfabética)."""
    with get_cursor() as cur:
        cur.execute("SELECT * FROM metas")
        metas = cur.fetchall()
        cur.execute(
            "SELECT mc.meta_id, c.id, c.nome, c.cor FROM metas_categorias mc "
            "JOIN categorias_meta c ON c.id = mc.categoria_id ORDER BY c.nome"
        )
        ligacoes = cur.fetchall()
    por_meta = {}
    for l in ligacoes:
        por_meta.setdefault(l["meta_id"], []).append({"id": l["id"], "nome": l["nome"], "cor": l["cor"]})
    for m in metas:
        m["categorias"] = por_meta.get(m["id"], [])
    return metas


# ---------- categorias (exclusivas das metas pessoais) ----------

class CategoriaDuplicada(Exception):
    pass


def listar_categorias():
    """Categorias com `em_uso`: quantas metas usam cada uma."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT c.id, c.nome, c.cor, COUNT(mc.meta_id) AS em_uso FROM categorias_meta c "
            "LEFT JOIN metas_categorias mc ON mc.categoria_id = c.id GROUP BY c.id ORDER BY c.nome"
        )
        return cur.fetchall()


def criar_categoria(nome, cor):
    """Devolve o id da nova categoria; levanta CategoriaDuplicada se o nome já existir."""
    try:
        with get_cursor() as cur:
            cur.execute("INSERT INTO categorias_meta (nome, cor) VALUES (%s, %s)", (nome, cor))
            return cur.lastrowid
    except IntegrityError as e:
        raise CategoriaDuplicada(nome) from e


def atualizar_categoria(categoria_id, nome, cor):
    try:
        with get_cursor() as cur:
            cur.execute("UPDATE categorias_meta SET nome=%s, cor=%s WHERE id=%s", (nome, cor, categoria_id))
    except IntegrityError as e:
        raise CategoriaDuplicada(nome) from e


def excluir_categoria(categoria_id):
    """Remove a categoria e, em cascata, a ligação dela com as metas (as metas permanecem)."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM categorias_meta WHERE id=%s", (categoria_id,))


def contar_metas_no_periodo(inicio, fim):
    """Retorna (concluidas, total) das metas com prazo entre `inicio` e `fim`; arquivadas ficam fora."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(status = 'concluida'), 0) AS concluidas "
            "FROM metas WHERE status IN ('ativa', 'concluida') AND prazo BETWEEN %s AND %s",
            (inicio, fim),
        )
        linha = cur.fetchone()
    return int(linha["concluidas"]), int(linha["total"])


def contar_metas_por_periodo(por, quantidade=12, hoje=None):
    """Metas por semana (domingo a sábado, `por="semana"`) ou mês (`por="mes"`) do prazo.

    Arquivadas e metas sem prazo ficam fora. Devolve os últimos `quantidade` períodos, do mais antigo
    ao atual, com zero nos vazios: dicts `inicio` (date), `concluidas`, `pendentes` (ativas ainda no
    prazo) e `atrasadas` (ativas com o prazo vencido, a mesma regra da tela de Metas).
    """
    hoje = hoje or date.today()
    if por == "semana":
        atual = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
        inicios = [atual - timedelta(weeks=i) for i in range(quantidade - 1, -1, -1)]
        # DAYOFWEEK: domingo = 1
        chave = "prazo - INTERVAL (DAYOFWEEK(prazo) - 1) DAY"
    elif por == "mes":
        indice = hoje.year * 12 + hoje.month - 1
        inicios = [date(i // 12, i % 12 + 1, 1) for i in range(indice - quantidade + 1, indice + 1)]
        chave = "prazo - INTERVAL (DAYOFMONTH(prazo) - 1) DAY"
    else:
        raise ValueError(por)
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {chave} AS inicio, "
            "COALESCE(SUM(status = 'concluida'), 0) AS concluidas, "
            "COALESCE(SUM(status = 'ativa' AND prazo >= %s), 0) AS pendentes, "
            "COALESCE(SUM(status = 'ativa' AND prazo < %s), 0) AS atrasadas "
            "FROM metas WHERE status IN ('ativa', 'concluida') AND prazo >= %s GROUP BY inicio",
            (hoje, hoje, inicios[0]),
        )
        por_inicio = {l["inicio"]: l for l in cur.fetchall()}
    vazio = {"concluidas": 0, "pendentes": 0, "atrasadas": 0}
    return [
        {"inicio": i, **{k: int(por_inicio.get(i, vazio)[k]) for k in vazio}}
        for i in inicios
    ]


def salvar_meta(meta_id, titulo, descricao, prioridade, prazo, tarefas, categoria_ids=(), progresso=None):
    """Cria (meta_id=None) ou atualiza a meta e sincroniza o checklist numa só transação.

    `tarefas` é a lista final, já na ordem desejada: dicts com `id` (None se nova),
    `descricao` e `prazo`. Tarefas do banco que não estão na lista são removidas.
    `categoria_ids` é a seleção final de categorias da meta.
    `progresso` é None (meta de tarefas) ou um dict com `tipo` (quantidade/valor), `objetivo`, `unidade`,
    `inicial`, `alvo` e `atual`. Em metas de quantidade/valor as tarefas são ignoradas e as existentes
    apagadas; em metas de tarefas as colunas de progresso voltam ao padrão.
    """
    p = progresso or {"tipo": "tarefas", "objetivo": "aumentar", "unidade": None, "inicial": None,
                      "alvo": None, "atual": None}
    if p["tipo"] != "tarefas":
        tarefas = []
    colunas = (p["tipo"], p["objetivo"], p["unidade"], p["inicial"], p["alvo"], p["atual"])
    with get_cursor() as cur:
        if meta_id is None:
            cur.execute(
                "INSERT INTO metas (titulo, descricao, prioridade, prazo, tipo_progresso, objetivo, unidade, "
                "valor_inicial, valor_alvo, valor_atual) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (titulo, descricao, prioridade, prazo, *colunas),
            )
            meta_id = cur.lastrowid
        else:
            cur.execute(
                "UPDATE metas SET titulo=%s, descricao=%s, prioridade=%s, prazo=%s, tipo_progresso=%s, "
                "objetivo=%s, unidade=%s, valor_inicial=%s, valor_alvo=%s, valor_atual=%s WHERE id=%s",
                (titulo, descricao, prioridade, prazo, *colunas, meta_id),
            )
            manter = [t["id"] for t in tarefas if t["id"] is not None]
            if manter:
                marcadores = ", ".join(["%s"] * len(manter))
                cur.execute(
                    f"DELETE FROM tarefas_meta WHERE meta_id=%s AND id NOT IN ({marcadores})",
                    (meta_id, *manter),
                )
            else:
                cur.execute("DELETE FROM tarefas_meta WHERE meta_id=%s", (meta_id,))
        for ordem, t in enumerate(tarefas):
            if t["id"] is None:
                cur.execute(
                    "INSERT INTO tarefas_meta (meta_id, descricao, prazo, ordem) VALUES (%s, %s, %s, %s)",
                    (meta_id, t["descricao"], t["prazo"], ordem),
                )
            else:
                cur.execute(
                    "UPDATE tarefas_meta SET descricao=%s, prazo=%s, ordem=%s WHERE id=%s",
                    (t["descricao"], t["prazo"], ordem, t["id"]),
                )
        cur.execute("DELETE FROM metas_categorias WHERE meta_id=%s", (meta_id,))
        for categoria_id in categoria_ids:
            cur.execute(
                "INSERT INTO metas_categorias (meta_id, categoria_id) VALUES (%s, %s)", (meta_id, categoria_id)
            )


def _valor_atual(cur, meta_id):
    cur.execute("SELECT valor_atual FROM metas WHERE id=%s", (meta_id,))
    return cur.fetchone()["valor_atual"]


def somar_valor(meta_id, delta, minimo=None):
    """Soma `delta` ao valor atual (atômico no SQL; `minimo` é o piso, ex.: 0 em quantidade).
    Devolve o novo valor."""
    with get_cursor() as cur:
        if minimo is None:
            cur.execute("UPDATE metas SET valor_atual = COALESCE(valor_atual, 0) + %s WHERE id=%s", (delta, meta_id))
        else:
            cur.execute(
                "UPDATE metas SET valor_atual = GREATEST(%s, COALESCE(valor_atual, 0) + %s) WHERE id=%s",
                (minimo, delta, meta_id),
            )
        return _valor_atual(cur, meta_id)


def definir_valor_atual(meta_id, valor, minimo=None):
    """Grava o valor atual (digitado pelo usuário); `minimo` é o piso. Devolve o valor gravado."""
    if minimo is not None:
        valor = max(valor, minimo)
    with get_cursor() as cur:
        cur.execute("UPDATE metas SET valor_atual=%s WHERE id=%s", (valor, meta_id))
        return _valor_atual(cur, meta_id)


def definir_status(meta_id, status):
    """Concluir grava a data (mantendo a original, se já houver); arquivar a preserva; reativar a zera."""
    with get_cursor() as cur:
        cur.execute(
            "UPDATE metas SET status=%s, data_conclusao = CASE %s "
            "WHEN 'concluida' THEN COALESCE(data_conclusao, NOW()) "
            "WHEN 'arquivada' THEN data_conclusao ELSE NULL END WHERE id=%s",
            (status, status, meta_id),
        )


def excluir_meta(meta_id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM metas WHERE id=%s", (meta_id,))


def listar_tarefas():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tarefas_meta ORDER BY ordem, id")
        return cur.fetchall()


def definir_tarefa_concluida(tarefa_id, concluida):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tarefas_meta SET concluida=%s, "
            "data_conclusao = IF(%s, NOW(), NULL) WHERE id=%s",
            (int(concluida), int(concluida), tarefa_id),
        )


def definir_ordem_tarefas(ids_na_ordem):
    with get_cursor() as cur:
        for ordem, tarefa_id in enumerate(ids_na_ordem):
            cur.execute("UPDATE tarefas_meta SET ordem=%s WHERE id=%s", (ordem, tarefa_id))
