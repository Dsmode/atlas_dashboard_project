from pathlib import Path

import streamlit.components.v1 as components

_componente = components.declare_component("checklist_sortable", path=str(Path(__file__).parent))


def checklist_sortable(itens, key):
    """Lista de tarefas com checkbox e alça de arrastar.

    `itens` leva id, descricao, prazo (texto) e concluida. Devolve o último evento do usuário, toggle
    (tarefa_id e concluida) ou ordem (lista de ids), sempre com um `id` único para quem chama tratar cada
    evento uma vez só."""
    return _componente(itens=itens, key=key, default=None)
