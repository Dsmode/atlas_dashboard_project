from datetime import date

from database.datas import intervalo_mes, intervalo_semana
from database.metas.modelo import STATUS
from database.texto import normalizar

PRIORIDADE_ORDEM = {"alta": 0, "media": 1, "baixa": 2}
STATUS_ORDEM = {"ativa": 0, "concluida": 1, "arquivada": 2}
STATUS_EXIBIDO = {**STATUS, "atrasada": "Atrasada"}

VISOES = ["todas", "semana", "mes", "atrasadas", "sem_prazo", "arquivadas"]
VISOES_NOME = {
    "semana": "Semanais", "mes": "Mensais", "atrasadas": "Atrasadas",
    "sem_prazo": "Sem prazo", "todas": "Todas", "arquivadas": "Arquivadas",
}


def filtrar_busca(metas, texto):
    termo = normalizar(texto.strip())
    if not termo:
        return list(metas)
    return [m for m in metas if termo in normalizar(m["titulo"]) or termo in normalizar(m["descricao"])]


def filtrar_por_categorias(metas, categoria_ids):
    ids = set(categoria_ids)
    if not ids:
        return list(metas)
    return [m for m in metas if ids & {c["id"] for c in m["categorias"]}]


def atrasada(meta, hoje):
    return meta["status"] == "ativa" and meta["prazo"] is not None and meta["prazo"] < hoje


def filtrar_visao(metas, visao, hoje):
    """Metas arquivadas só aparecem na visão "arquivadas"."""
    if visao == "arquivadas":
        return [m for m in metas if m["status"] == "arquivada"]
    metas = [m for m in metas if m["status"] != "arquivada"]
    if visao == "semana":
        ini, fim = intervalo_semana(hoje)
        return [m for m in metas if m["prazo"] and ini <= m["prazo"] <= fim]
    if visao == "mes":
        ini, fim = intervalo_mes(hoje)
        return [m for m in metas if m["prazo"] and ini <= m["prazo"] <= fim]
    if visao == "atrasadas":
        return [m for m in metas if atrasada(m, hoje)]
    if visao == "sem_prazo":
        return [m for m in metas if m["prazo"] is None]
    return metas


def situacao(meta, hoje):
    """Situação mostrada no cartão: ativa, atrasada, concluída ou arquivada."""
    return "atrasada" if atrasada(meta, hoje) else meta["status"]


def resumo(metas, hoje):
    """Números dos três painéis. As arquivadas ficam de fora."""
    semana = filtrar_visao(metas, "semana", hoje)
    mes = filtrar_visao(metas, "mes", hoje)
    def feitas(lista):
        return sum(1 for m in lista if m["status"] == "concluida")

    return {
        "semana_feitas": feitas(semana),
        "semana_faltam": len(semana) - feitas(semana),
        "mes_feitas": feitas(mes),
        "mes_total": len(mes),
        "atrasadas": len(filtrar_visao(metas, "atrasadas", hoje)),
    }


def ordenar(metas):
    """Prioridade (alta primeiro), depois situação (ativas antes das concluídas) e por fim o prazo."""
    return sorted(
        metas,
        key=lambda m: (
            PRIORIDADE_ORDEM[m["prioridade"]],
            STATUS_ORDEM[m["status"]],
            m["prazo"] or date.max,
        ),
    )
