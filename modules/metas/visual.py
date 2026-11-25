from html import escape

from database.cores import COR_NEUTRA, cor_texto, cor_valida

COR_GERAL = COR_NEUTRA


def chip(categoria):
    return (
        f'<span class="cat-chip" style="background:{cor_valida(categoria["cor"])};color:{cor_texto(categoria["cor"])}">'
        f'{escape(categoria["nome"])}</span>'
    )


def chips(categorias):
    return f'<div class="cat-chips">{"".join(chip(c) for c in categorias)}</div>' if categorias else ""


def fmt_data(d):
    return d.strftime("%d/%m/%Y") if d else "sem prazo"
