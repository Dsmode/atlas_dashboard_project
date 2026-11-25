import re

COR_PADRAO = "#b44cff"
COR_NEUTRA = "#8d8d9c"

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


TEXTO_ESCURO = "#14141a"
TEXTO_CLARO = "#ffffff"


def cor_valida(valor):
    return valor.lower() if isinstance(valor, str) and _HEX.fullmatch(valor) else COR_PADRAO


def _luminancia(cor):
    canais = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cor_texto(fundo):
    """Branco ou escuro sobre `fundo`. O branco fica enquanto tiver o contraste 4,5:1 das diretrizes de
    acessibilidade; abaixo disso entra o escuro."""
    contraste_claro = 1.05 / (_luminancia(cor_valida(fundo)) + 0.05)
    return TEXTO_CLARO if contraste_claro >= 4.5 else TEXTO_ESCURO
