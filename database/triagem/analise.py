"""A análise da caixa inteira (classificação, cards do usuário, resumos), sem Streamlit. A tela a guarda em cache e a
triagem agendada a calcula a cada execução, então os dois usam o mesmo código."""
from . import classificacao, regras, repo


def analisavel(e):
    """Enviados e o que já está na lixeira do Gmail não entram em card nem na análise de termos."""
    return not e["enviado"] and not e["lixeira"]


def calcular():
    """Todos os e-mails, a classificação de cada um, os cards do usuário e o resumo de todos os cards."""
    repo.garantir_protegidos_padrao(classificacao.PROTEGIDOS_PADRAO)
    repo.garantir_palavras_salvam_padrao(classificacao.PALAVRAS_SALVAM_PADRAO)
    protegidos = {p["valor"] for p in repo.listar_protegidos()}
    emails = repo.emails_para_classificar()
    preparados = {e["id"]: regras.preparar(e) for e in emails if analisavel(e)}
    cards = repo.listar_cards()
    salvam = [regras.sem_acento(p) for p in repo.listar_palavras_salvam()]
    resultado = classificacao.classificar(
        emails, protegidos, classificacao.ids_que_casam_com_algum(cards, preparados), salvam, preparados,
        {b["valor"] for b in repo.listar_bloqueados()})
    membros = classificacao.membros_dos_cards(cards, preparados, resultado)
    return {
        "emails": emails, "preparados": preparados, "classificacao": resultado, "cards": cards, "membros": membros,
        "resumo": classificacao.resumo_por_card(emails, resultado),
        "resumo_cards": {c["id"]: classificacao.resumo_de_ids(emails, membros[c["id"]]) for c in cards},
        "protegidos": sorted(protegidos),
    }


def ids_do_card_fixo(caixa, card):
    return {i for i, (c, _) in caixa["classificacao"].items() if c == card}
