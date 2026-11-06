from html import escape

from database.cores import COR_NEUTRA, cor_valida

COR_GERAL = COR_NEUTRA


def cor_texto(cor):
    cor = cor_valida(cor)
    r, g, b = (int(cor[i:i + 2], 16) for i in (1, 3, 5))
    return "#14141a" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"


def chip(categoria):
    return (
        f'<span class="cat-chip" style="background:{cor_valida(categoria["cor"])};color:{cor_texto(categoria["cor"])}">'
        f'{escape(categoria["nome"])}</span>'
    )


def chips(categorias):
    return f'<div class="cat-chips">{"".join(chip(c) for c in categorias)}</div>' if categorias else ""


def fmt_data(d):
    return d.strftime("%d/%m/%Y") if d else "sem prazo"
