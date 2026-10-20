from database.connection import get_cursor


def listar_metas():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM metas")
        return cur.fetchall()


def criar_meta(titulo, descricao, prioridade, prazo):
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO metas (titulo, descricao, prioridade, prazo) VALUES (%s, %s, %s, %s)",
            (titulo, descricao, prioridade, prazo),
        )


def atualizar_meta(meta_id, titulo, descricao, prioridade, prazo):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE metas SET titulo=%s, descricao=%s, prioridade=%s, prazo=%s WHERE id=%s",
            (titulo, descricao, prioridade, prazo, meta_id),
        )


def definir_status(meta_id, status):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE metas SET status=%s, "
            "data_conclusao = IF(%s = 'concluida', NOW(), NULL) WHERE id=%s",
            (status, status, meta_id),
        )


def excluir_meta(meta_id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM metas WHERE id=%s", (meta_id,))


def listar_tarefas():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM tarefas_meta ORDER BY concluida, id")
        return cur.fetchall()


def criar_tarefa(meta_id, descricao, prazo):
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO tarefas_meta (meta_id, descricao, prazo) VALUES (%s, %s, %s)",
            (meta_id, descricao, prazo),
        )


def definir_tarefa_concluida(tarefa_id, concluida):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tarefas_meta SET concluida=%s, "
            "data_conclusao = IF(%s, NOW(), NULL) WHERE id=%s",
            (int(concluida), int(concluida), tarefa_id),
        )


def excluir_tarefa(tarefa_id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM tarefas_meta WHERE id=%s", (tarefa_id,))
