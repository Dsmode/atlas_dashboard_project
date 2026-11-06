from decimal import Decimal

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")
VALOR_MAX = Decimal("999999999999.99")


def fmt_brl(valor, sinal=False):
    valor = Decimal(valor).quantize(CENTAVO)
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    prefixo = "-" if valor < 0 else ("+" if sinal and valor > 0 else "")
    return f"{prefixo}R$ {texto}"
