from pathlib import Path

import streamlit.components.v1 as components

_componente = components.declare_component("checklist_sortable", path=str(Path(__file__).parent))


def checklist_sortable(itens, key):
    """Lista de tarefas com checkbox e alça de arrastar.

    `itens`: dicts com `id`, `descricao`, `prazo` (texto) e `concluida`. Devolve o último evento
    do usuário — {"evento": "toggle", "tarefa_id", "concluida"} ou {"evento": "ordem", "ordem": [ids]} —
    sempre com um `id` único, para quem chama processar cada evento uma só vez.
    """
    return _componente(itens=itens, key=key, default=None)
