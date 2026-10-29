"""Regra de progresso das Metas Pessoais (tarefas, quantidade e valor em R$).

Módulo puro: sem Streamlit e sem banco, para ser usado pelo repositório, pela importação e pelas telas.
Valores monetários e de quantidade são `Decimal` (quantidade guarda sempre inteiros).
"""
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

TIPOS = ("tarefas", "quantidade", "valor")
OBJETIVOS = ("aumentar", "reduzir")
LIMITE = Decimal("999999999999.99")  # cabe em DECIMAL(14,2)

_CENTAVO = Decimal("0.01")


def _numero(valor):
    return Decimal(0) if valor is None else Decimal(valor)


def progresso(meta, tarefas):
    """Estado do progresso da meta: dict com `atual`, `alvo`, `pct` (inteiro de 0 a 100) e `atingida`.

    Aumentar parte de zero (quem já tem R$ 500 de R$ 5.000 está em 10%); reduzir mede o caminho da partida
    até o alvo. O percentual só chega a 100 quando a meta é de fato atingida."""
    if meta["tipo_progresso"] == "tarefas":
        total = len(tarefas)
        atual = sum(1 for t in tarefas if t["concluida"])
        alvo, atingida = total, total > 0 and atual == total
        razao = Decimal(atual) / total if total else Decimal(0)
    else:
        atual, alvo = _numero(meta["valor_atual"]), _numero(meta["valor_alvo"])
        if meta["objetivo"] == "reduzir":
            inicial = _numero(meta["valor_inicial"])
            atingida = atual <= alvo
            distancia = inicial - alvo
            razao = (inicial - atual) / distancia if distancia > 0 else Decimal(0)
        else:
            atingida = atual >= alvo
            razao = atual / alvo if alvo > 0 else Decimal(0)
    razao = min(max(razao, Decimal(0)), Decimal(1))
    pct = 100 if atingida else min(99, int((razao * 100).to_integral_value(rounding=ROUND_FLOOR)))
    return {"atual": atual, "alvo": alvo, "pct": pct, "atingida": atingida}


def fmt_brl(valor):
    """R$ 1.200,00 (negativo: -R$ 50,00)."""
    valor = Decimal(valor).quantize(_CENTAVO)
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if valor < 0 else ''}R$ {texto}"


def fmt_qtd(valor):
    """Quantidade inteira, com ponto de milhar."""
    return f"{int(valor):,}".replace(",", ".")


def validar(tipo, objetivo, alvo, inicial, atual):
    """Mensagem de erro (em português) para os dados de progresso, ou None se estiverem corretos."""
    if tipo == "tarefas":
        return None
    if alvo is None or alvo <= 0:
        return "Informe um alvo maior que zero."
    valores = [v for v in (alvo, inicial, atual) if v is not None]
    if tipo == "quantidade":
        if any(v != v.to_integral_value() for v in valores):
            return "Quantidade aceita só números inteiros."
        if any(v < 0 for v in (inicial, atual) if v is not None):
            return "Quantidade não pode ser negativa."
    if objetivo == "reduzir" and (inicial is None or inicial <= alvo):
        return "Em uma meta de redução, o valor de partida deve ser maior que o alvo."
    if any(abs(v) > LIMITE for v in valores):
        return "Valor grande demais."
    return None


def ritmo(meta, hoje):
    """Quanto falta e o ritmo necessário até o prazo; None quando não se aplica.

    Só para metas ativas de quantidade/valor, com prazo e ainda não atingidas. Até 14 dias o ritmo é por
    dia, até 90 por semana, acima disso por mês."""
    if meta["tipo_progresso"] == "tarefas" or meta["status"] != "ativa" or not meta["prazo"]:
        return None
    p = progresso(meta, [])
    if p["atingida"]:
        return None
    faltam = p["atual"] - p["alvo"] if meta["objetivo"] == "reduzir" else p["alvo"] - p["atual"]
    monetario = meta["tipo_progresso"] == "valor"
    texto = fmt_brl(faltam) if monetario else " ".join(filter(None, [fmt_qtd(faltam), meta.get("unidade")]))
    dias = (meta["prazo"] - hoje).days
    if dias < 0:
        return f"Prazo vencido · faltam {texto}"
    if dias == 0:
        return f"O prazo é hoje · faltam {texto}"
    if dias <= 14:
        periodos, nome = dias, "dia"
    elif dias <= 90:
        periodos, nome = -(-dias // 7), "semana"
    else:
        periodos, nome = -(-dias // 30), "mês"
    por_periodo = faltam / periodos
    if monetario:
        por_periodo = fmt_brl(por_periodo.quantize(_CENTAVO, rounding=ROUND_CEILING))
    else:
        por_periodo = fmt_qtd(por_periodo.to_integral_value(rounding=ROUND_CEILING))
    return f"Faltam {texto} · cerca de {por_periodo} por {nome}"
