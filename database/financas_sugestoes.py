"""Sugestão automática de categoria e tipo (fixo/variável) para as linhas importadas.

Ordem de decisão: regras do usuário → histórico do usuário → dicionário de palavras-chave → padrão ("Outros").
Funções puras: o contexto (regras, histórico, categorias) é montado pela tela a partir do banco.
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from database.financas_importacao import normalizar

# nome (normalizado) da categoria padrão -> palavras inteiras já normalizadas
PALAVRAS_CHAVE = {
    "alimentacao": ("ifood", "99food", "restaurante", "lanchonete", "padaria", "mercado", "supermercado",
                    "casa de sucos", "pizzaria", "burger", "acougue", "hortifruti"),
    "transporte": ("posto", "uber", "99 pop", "combustivel", "estacionamento", "pedagio"),
    "saude": ("drogaria", "farmacia", "dro", "clinica", "laboratorio"),
    "assinaturas": ("netflix", "spotify", "crunchyroll", "google", "youtube", "prime", "disney", "subscription"),
    "educacao": ("faculdade", "escola", "curso"),
    "casa": ("condominio", "aluguel", "energia", "agua", "internet"),
    "lazer": ("cinema", "ingresso", "steam", "playstation"),
}
_PADROES = tuple(
    (categoria, tuple(re.compile(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])") for p in palavras))
    for categoria, palavras in PALAVRAS_CHAVE.items()
)
OUTROS = "outros"


@dataclass(frozen=True)
class Contexto:
    regras: tuple  # linhas de fin_regras: padrao, categoria_id, tipo, ignorar
    historico: dict  # descrição normalizada -> {"categoria_id", "tipo"} do lançamento mais recente
    recorrentes: frozenset  # descrições normalizadas recorrentes (ver `recorrentes`)
    categorias_gasto: dict  # nome normalizado -> id
    categorias_entrada: dict


@dataclass(frozen=True)
class Sugestao:
    categoria_id: int | None
    tipo: str
    ignorar: bool
    origem: str  # 'regra' | 'historico' | 'palavra' | 'padrao'


def _palavra(norm, categorias):
    for nome, padroes in _PADROES:
        if any(p.search(norm) for p in padroes):
            return categorias.get(nome, categorias.get(OUTROS))
    return None


def sugerir(descricao: str, entrada: bool, ctx: Contexto) -> Sugestao:
    norm = normalizar(descricao)
    categorias = ctx.categorias_entrada if entrada else ctx.categorias_gasto
    validas = set(categorias.values())

    categoria, tipo, origem = None, None, "padrao"
    ligado = ctx.historico.get(norm)
    if ligado and ligado.get("categoria_id") in validas:
        categoria, origem = ligado["categoria_id"], "historico"
        if ligado.get("tipo") in ("fixo", "variavel"):
            tipo = ligado["tipo"]
    if categoria is None and not entrada:
        achada = _palavra(norm, categorias)
        if achada is not None:
            categoria, origem = achada, "palavra"
    if categoria is None:
        categoria = categorias.get(OUTROS)

    ignorar = False
    regras = [r for r in ctx.regras if r["padrao"] and r["padrao"] in norm]
    if regras:
        regra = max(regras, key=lambda r: len(r["padrao"]))
        origem = "regra"
        ignorar = bool(regra.get("ignorar"))
        if regra.get("categoria_id") in validas:
            categoria = regra["categoria_id"]
        if regra.get("tipo") in ("fixo", "variavel"):
            tipo = regra["tipo"]

    if entrada:
        tipo = "entrada"
    elif tipo is None:
        tipo = "fixo" if norm in ctx.recorrentes else "variavel"
    return Sugestao(categoria_id=categoria, tipo=tipo, ignorar=ignorar, origem=origem)


def recorrentes(lancamentos: Sequence[dict], mes_atual) -> frozenset:
    """Descrições (normalizadas) de gastos que apareceram em ≥ 2 meses anteriores a `mes_atual` com valor
    semelhante (diferença de até 10%). `lancamentos`: dicts com descricao, data, valor e, opcionalmente, tipo."""
    por_descricao = {}
    for l in lancamentos:
        if not l.get("descricao") or l.get("tipo") == "entrada" or l["data"] >= mes_atual:
            continue
        por_descricao.setdefault(normalizar(l["descricao"]), {}).setdefault(
            (l["data"].year, l["data"].month), []).append(Decimal(l["valor"]))
    achados = set()
    for desc, meses in por_descricao.items():
        itens = [(m, v) for m, valores in meses.items() for v in valores]
        if any(m1 != m2 and abs(v1 - v2) <= Decimal("0.10") * max(v1, v2)
               for i, (m1, v1) in enumerate(itens) for (m2, v2) in itens[i + 1:]):
            achados.add(desc)
    return frozenset(achados)
