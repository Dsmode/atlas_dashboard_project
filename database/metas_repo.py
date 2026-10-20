from database.connection import get_cursor


def listar_metas():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM metas")
        return cur.fetchall()


def salvar_meta(meta_id, titulo, descricao, prioridade, prazo, tarefas):
    """Cria (meta_id=None) ou atualiza a meta e sincroniza o checklist numa só transação.

    `tarefas` é a lista final, já na ordem desejada: dicts com `id` (None se nova),
    `descricao` e `prazo`. Tarefas do banco que não estão na lista são removidas.
    """
    with get_cursor() as cur:
        if meta_id is None:
            cur.execute(
                "INSERT INTO metas (titulo, descricao, prioridade, prazo) VALUES (%s, %s, %s, %s)",
                (titulo, descricao, prioridade, prazo),
            )
            meta_id = cur.lastrowid
        else:
            cur.execute(
                "UPDATE metas SET titulo=%s, descricao=%s, prioridade=%s, prazo=%s WHERE id=%s",
                (titulo, descricao, prioridade, prazo, meta_id),
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
        cur.execute("SELECT * FROM tarefas_meta ORDER BY ordem, id")
        return cur.fetchall()


def definir_tarefa_concluida(tarefa_id, concluida):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE tarefas_meta SET concluida=%s, "
            "data_conclusao = IF(%s, NOW(), NULL) WHERE id=%s",
            (int(concluida), int(concluida), tarefa_id),
        )
