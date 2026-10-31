"""Regras do Controle Financeiro sem banco nem tela (meses, totais, gráficos e cópia de fixos).

Um lançamento é o dict devolvido por `financas_repo.listar_lancamentos`: `tipo` ('entrada', 'fixo' ou
'variavel'), `data`, `valor` (Decimal, sempre positivo), `categoria_id`, `categoria_nome`, `categoria_cor`...
"""
import calendar
from collections import Counter
from datetime import date
from decimal import Decimal

CENTAVO = Decimal("0.01")
ZERO = Decimal("0")

TIPOS = ("entrada", "fixo", "variavel")
TIPOS_GASTO = ("fixo", "variavel")
FORMAS = ("pix", "debito", "credito", "dinheiro")

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

DESCRICAO_MAX = 80
OBSERVACAO_MAX = 255
VALOR_MAX = Decimal("999999999999.99")  # DECIMAL(14, 2)


# ---------- meses ----------

def inicio_mes(d):
    return date(d.year, d.month, 1)


def somar_meses(mes, n):
    """Primeiro dia do mês `n` meses depois de `mes` (n negativo volta)."""
    total = mes.year * 12 + mes.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def fim_mes(mes):
    return date(mes.year, mes.month, calendar.monthrange(mes.year, mes.month)[1])


def meses_ate(mes, quantidade):
    """Os `quantidade` meses que terminam em `mes`, do mais antigo ao mais novo."""
    mes = inicio_mes(mes)
    return [somar_meses(mes, -i) for i in range(quantidade - 1, -1, -1)]


def nome_mes(mes):
    """'Novembro 2026'."""
    return f"{MESES[mes.month - 1]} {mes.year}"


def mes_curto(mes, com_ano=False):
    """'nov' ou 'nov/26'."""
    return f"{MESES_CURTOS[mes.month - 1]}/{mes.year % 100:02d}" if com_ano else MESES_CURTOS[mes.month - 1]


def data_no_mes(dia, mes):
    """O mesmo dia no `mes`; se o mês for mais curto (31 → fevereiro), o último dia dele."""
    return date(mes.year, mes.month, min(dia, calendar.monthrange(mes.year, mes.month)[1]))


# ---------- dinheiro ----------

def fmt_brl(valor, sinal=False):
    """R$ 1.200,00; negativo -R$ 50,00; com `sinal`, positivo ganha '+'."""
    valor = Decimal(valor).quantize(CENTAVO)
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    prefixo = "-" if valor < 0 else ("+" if sinal and valor > 0 else "")
    return f"{prefixo}R$ {texto}"


def para_decimal(numero):
    """Campos numéricos do Streamlit devolvem float: converte sem herdar erro de ponto flutuante.

    Acima de VALOR_MAX o número volta sem arredondar (o quantize estouraria a precisão); a validação recusa.
    """
    valor = Decimal(str(round(float(numero), 2)))
    return valor.quantize(CENTAVO) if abs(valor) <= VALOR_MAX else valor


def fmt_pct(valor):
    """38,0%."""
    return f"{valor:.1f}%".replace(".", ",")


def e_gasto(lancamento):
    return lancamento["tipo"] in TIPOS_GASTO


def grupo_categoria(tipo):
    """Entradas usam as categorias 'entrada'; fixos e variáveis dividem as de 'gasto'."""
    return "entrada" if tipo == "entrada" else "gasto"


# ---------- validação ----------

def validar_lancamento(tipo, valor, forma, banco_id, tipo_categoria, descricao=None, observacao=None):
    """Mensagem de erro para o usuário, ou None se estiver tudo certo."""
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


# ---------- resumo e gráficos ----------

def resumo_mes(lancamentos):
    """Entradas, saídas, saldo e quanto da renda foi gasto (`pct_gasto` None se não houve entrada)."""
    entradas = sum((l["valor"] for l in lancamentos if not e_gasto(l)), ZERO)
    saidas = sum((l["valor"] for l in lancamentos if e_gasto(l)), ZERO)
    pct = (saidas / entradas * 100).quantize(Decimal("0.1")) if entradas else None
    return {"entradas": entradas, "saidas": saidas, "saldo": entradas - saidas, "pct_gasto": pct}


def entradas_saidas(totais, meses):
    """Uma linha por mês (zeros onde não houve lançamento). `totais`: {mês: (entradas, saídas)}."""
    linhas = []
    for mes in meses:
        entradas, saidas = totais.get(mes, (ZERO, ZERO))
        linhas.append({"mes": mes, "entradas": entradas, "saidas": saidas, "saldo": entradas - saidas})
    return linhas


def fluxo_caixa(saldo_inicial, totais, meses):
    """Saldo acumulado no fim de cada mês: saldo inicial + tudo o que entrou menos tudo o que saiu até ali.

    Meses anteriores à janela também contam (o saldo não recomeça em zero no primeiro mês mostrado).
    """
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
    """Gastos (fixos e variáveis) somados por categoria, do maior para o menor, com percentual."""
    grupos = {}
    for l in lancamentos:
        if e_gasto(l):
            g = grupos.setdefault(l["categoria_id"], {
                "id": l["categoria_id"], "nome": l["categoria_nome"], "cor": l["categoria_cor"], "valor": ZERO,
            })
            g["valor"] += l["valor"]
    return _com_percentual(list(grupos.values()))


def gastos_por_tipo(lancamentos):
    """Gastos fixos × variáveis, com percentual (os dois sempre presentes, mesmo zerados; `id` é o tipo)."""
    grupos = [
        {"id": tipo, "nome": nome, "valor": sum((l["valor"] for l in lancamentos if l["tipo"] == tipo), ZERO)}
        for tipo, nome in (("fixo", "Fixos"), ("variavel", "Variáveis"))
    ]
    return _com_percentual(grupos)


# ---------- copiar gastos fixos do mês anterior ----------

def _assinatura(l):
    return ((l.get("descricao") or "").strip().lower(), l["categoria_id"], l["valor"])


def plano_copia_fixos(fixos_anteriores, fixos_atuais, mes_destino):
    """Cada fixo do mês anterior com a data no `mes_destino` e `repetido` = já existe um igual no destino.

    Igual = mesma descrição (sem caixa), categoria e valor. Conta por quantidade: dois iguais na origem e um
    no destino deixam só um como repetido. Os repetidos vêm desmarcados na tela.
    """
    existentes = Counter(_assinatura(l) for l in fixos_atuais)
    plano = []
    for l in sorted(fixos_anteriores, key=lambda l: (l["data"], l["id"])):
        novo = dict(l)
        novo["data"] = data_no_mes(l["data"].day, mes_destino)
        assinatura = _assinatura(l)
        novo["repetido"] = existentes[assinatura] > 0
        existentes[assinatura] -= 1
        plano.append(novo)
    return plano
