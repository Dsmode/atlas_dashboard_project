import re

COR_PADRAO = "#b44cff"
COR_NEUTRA = "#8d8d9c"

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def cor_valida(valor):
    return valor.lower() if isinstance(valor, str) and _HEX.fullmatch(valor) else COR_PADRAO
