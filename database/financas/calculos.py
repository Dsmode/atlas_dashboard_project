"""Regras do Controle Financeiro sem banco nem tela: meses, totais, gráficos e cópia de fixos.

Um lançamento é o dict de `financas.repo.listar_lancamentos`: tipo ('entrada', 'fixo' ou 'variavel'), data,
valor (Decimal sempre positivo), categoria_id, categoria_nome, categoria_cor..."""

import calendar
from collections import Counter
from datetime import date
from decimal import Decimal

from database.dinheiro import CENTAVO, VALOR_MAX, ZERO

TIPOS = ("entrada", "fixo", "variavel")
TIPOS_GASTO = ("fixo", "variavel")
FORMAS = ("pix", "debito", "credito", "dinheiro")

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

DESCRICAO_MAX = 80
OBSERVACAO_MAX = 255


def inicio_mes(d):
    return date(d.year, d.month, 1)


def somar_meses(mes, n):
    """Primeiro dia do mês, `n` meses à frente (n negativo volta)."""
    total = mes.year * 12 + mes.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def fim_mes(mes):
    return date(mes.year, mes.month, calendar.monthrange(mes.year, mes.month)[1])


def meses_ate(mes, quantidade):
    mes = inicio_mes(mes)
    return [somar_meses(mes, -i) for i in range(quantidade - 1, -1, -1)]


def nome_mes(mes):
    return f"{MESES[mes.month - 1]} {mes.year}"


def mes_curto(mes, com_ano=False):
    return f"{MESES_CURTOS[mes.month - 1]}/{mes.year % 100:02d}" if com_ano else MESES_CURTOS[mes.month - 1]


def data_no_mes(dia, mes):
    """Mesmo dia em outro mês; num mês mais curto (31 de março para fevereiro), cai no último dia."""
    return date(mes.year, mes.month, min(dia, calendar.monthrange(mes.year, mes.month)[1]))


def para_decimal(numero):
    """O Streamlit entrega float; arredondar antes evita herdar o erro de ponto flutuante. Acima de VALOR_MAX o
    número volta sem quantizar (estouraria a precisão) e a validação o recusa."""
    valor = Decimal(str(round(float(numero), 2)))
    return valor.quantize(CENTAVO) if abs(valor) <= VALOR_MAX else valor


def fmt_pct(valor):
    return f"{valor:.1f}%".replace(".", ",")


def e_gasto(lancamento):
    return lancamento["tipo"] in TIPOS_GASTO


def grupo_categoria(tipo):
    """Entradas usam categorias de entrada; fixos e variáveis dividem as de gasto."""
    return "entrada" if tipo == "entrada" else "gasto"


def validar_lancamento(tipo, valor, forma, banco_id, tipo_categoria, descricao=None, observacao=None):
    if tipo not in TIPOS:
        return "Escolha o tipo do lançamento."
    if forma not in FORMAS:
        return "Escolha a forma de pagamento."
    if valor is None or valor <= 0:
        return "Informe um valor maior que zero."
    if valor > VALOR_MAX:
        return "Valor alto demais."
    if tipo_categoria != grupo_categoria(tipo):
        return "Escolha uma categoria do mesmo tipo do lançamento."
    if forma == "dinheiro" and banco_id is not None:
        return "Pagamento em dinheiro não tem banco."
    if descricao and len(descricao) > DESCRICAO_MAX:
        return f"A descrição pode ter até {DESCRICAO_MAX} caracteres."
    if observacao and len(observacao) > OBSERVACAO_MAX:
        return f"A observação pode ter até {OBSERVACAO_MAX} caracteres."
    return None


def resumo_mes(lancamentos):
    entradas = sum((lanc["valor"] for lanc in lancamentos if not e_gasto(lanc)), ZERO)
    saidas = sum((lanc["valor"] for lanc in lancamentos if e_gasto(lanc)), ZERO)
    pct = (saidas / entradas * 100).quantize(Decimal("0.1")) if entradas else None
    return {"entradas": entradas, "saidas": saidas, "saldo": entradas - saidas, "pct_gasto": pct}


def entradas_saidas(totais, meses):
    linhas = []
    for mes in meses:
        entradas, saidas = totais.get(mes, (ZERO, ZERO))
        linhas.append({"mes": mes, "entradas": entradas, "saidas": saidas, "saldo": entradas - saidas})
    return linhas


def fluxo_caixa(saldo_inicial, totais, meses):
    """Saldo acumulado no fim de cada mês. Os meses anteriores à janela entram na conta, então o saldo não
    recomeça do zero no primeiro mês mostrado."""
    linhas = []
    for mes in meses:
        acumulado = saldo_inicial + sum((e - s for m, (e, s) in totais.items() if m <= mes), ZERO)
        entradas, saidas = totais.get(mes, (ZERO, ZERO))
        linhas.append({"mes": mes, "saldo": acumulado, "resultado": entradas - saidas})
    return linhas


def _com_percentual(grupos):
    total = sum((g["valor"] for g in grupos), ZERO)
    for g in grupos:
        g["pct"] = (g["valor"] / total * 100).quantize(Decimal("0.1")) if total else ZERO
    return sorted(grupos, key=lambda g: (-g["valor"], g["nome"]))


def gastos_por_categoria(lancamentos):
    grupos = {}
    for lanc in lancamentos:
        if e_gasto(lanc):
            g = grupos.setdefault(lanc["categoria_id"], {
                "id": lanc["categoria_id"], "nome": lanc["categoria_nome"], "cor": lanc["categoria_cor"], "valor": ZERO,
            })
            g["valor"] += lanc["valor"]
    return _com_percentual(list(grupos.values()))


def gastos_por_tipo(lancamentos):
    grupos = [
        {"id": tipo, "nome": nome, "valor": sum((lanc["valor"] for lanc in lancamentos if lanc["tipo"] == tipo), ZERO)}
        for tipo, nome in (("fixo", "Fixos"), ("variavel", "Variáveis"))
    ]
    return _com_percentual(grupos)


def _assinatura(lanc):
    return ((lanc.get("descricao") or "").strip().lower(), lanc["categoria_id"], lanc["valor"])


def plano_copia_fixos(fixos_anteriores, fixos_atuais, mes_destino):
    """Cada fixo do mês anterior com a data no mês de destino e `repetido` quando já existe um igual lá
    (mesma descrição sem caixa, categoria e valor). A conta é por quantidade: dois fixos iguais na origem e
    um no destino deixam só um como repetido. Os repetidos vêm desmarcados na tela."""
    existentes = Counter(_assinatura(lanc) for lanc in fixos_atuais)
    plano = []
    for lanc in sorted(fixos_anteriores, key=lambda lanc: (lanc["data"], lanc["id"])):
        novo = dict(lanc)
        novo["data"] = data_no_mes(lanc["data"].day, mes_destino)
        assinatura = _assinatura(lanc)
        novo["repetido"] = existentes[assinatura] > 0
        existentes[assinatura] -= 1
        plano.append(novo)
    return plano
