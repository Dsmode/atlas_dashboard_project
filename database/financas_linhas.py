"""Linhas da revisão da importação: monta, resume e converte em lançamentos (regras puras, sem banco).

Fluxo: `preparar_compras` (recorta o intervalo e soma o IOF) → a tela consulta as chaves já existentes →
`montar_linhas` (descrição, forma, sugestão, ignoradas, duplicadas, erros) → o usuário edita →
`para_lancamentos` (só o que vai ser gravado).
"""
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Sequence

from database.financas_calculos import VALOR_MAX
from database.financas_importacao import (
    Compra, chave_externa, forma_da_linha, fundir_iof, limpar_descricao, marcar_duplicados, motivo_ignorada,
    normalizar, observacao_lancamento, recortar,
)
from database.financas_sugestoes import Contexto, sugerir
from database.ofx_leitor import ExtratoOfx

ZERO = Decimal("0")
SITUACOES_GRAVAVEIS = ("novo", "ignorado")  # duplicadas e com erro nunca são gravadas


@dataclass
class LinhaRevisao:
    indice: int
    data: date
    descricao: str  # já limpa; o usuário pode editar
    texto_original: str
    valor: Decimal  # positivo (compra + IOF)
    entrada: bool
    forma: str
    tipo: str  # 'entrada' | 'fixo' | 'variavel'
    categoria_id: int | None
    importar: bool
    situacao: str  # 'novo' | 'duplicado' | 'ignorado' | 'erro'
    motivo: str
    iof: Decimal
    chave: str


def preparar_compras(extrato: ExtratoOfx, inicio: date, fim: date) -> list:
    """Linhas do arquivo dentro do intervalo, com o IOF já somado à compra."""
    return fundir_iof(recortar(extrato.transacoes, inicio, fim))


def montar_linhas(compras: Sequence[Compra], origem: str, meu_nome: str, ctx: Contexto,
                  existentes: Counter) -> list:
    """Uma linha de revisão por compra. `existentes` (chave → quantas já estão no banco) marca as duplicadas."""
    duplicadas = marcar_duplicados([chave_externa(c.principal) for c in compras], existentes)
    linhas = []
    for indice, (compra, duplicada) in enumerate(zip(compras, duplicadas)):
        t = compra.principal
        entrada = t.valor > 0
        descricao = limpar_descricao(t.texto)
        sugestao = sugerir(descricao, entrada, ctx)
        motivo = motivo_ignorada(origem, entrada, t.texto, meu_nome)
        if not motivo and sugestao.ignorar:
            motivo = "Regra: ignorar"
        if compra.valor == ZERO:
            situacao, motivo = "erro", "Valor zero"
        elif compra.valor > VALOR_MAX:
            situacao, motivo = "erro", "Valor acima do limite"
        elif duplicada:
            situacao, motivo = "duplicado", "Já importado antes"
        elif motivo:
            situacao = "ignorado"
        else:
            situacao = "novo"
        linhas.append(LinhaRevisao(
            indice=indice, data=t.data, descricao=descricao, texto_original=t.texto, valor=compra.valor,
            entrada=entrada, forma=forma_da_linha(origem, t.texto), tipo=sugestao.tipo,
            categoria_id=sugestao.categoria_id, importar=situacao == "novo", situacao=situacao, motivo=motivo,
            iof=compra.iof, chave=chave_externa(t),
        ))
    return linhas


def resumo(linhas: Sequence[LinhaRevisao]) -> dict:
    """Contagens por situação e totais do que será gravado (conforme as marcações atuais)."""
    gravar = [l for l in linhas if l.importar and l.situacao in SITUACOES_GRAVAVEIS]
    entradas = sum((l.valor for l in gravar if l.entrada), ZERO)
    saidas = sum((l.valor for l in gravar if not l.entrada), ZERO)
    return {
        "novos": sum(1 for l in linhas if l.situacao == "novo"),
        "duplicados": sum(1 for l in linhas if l.situacao == "duplicado"),
        "ignorados": sum(1 for l in linhas if l.situacao == "ignorado"),
        "erros": sum(1 for l in linhas if l.situacao == "erro"),
        "a_importar": len(gravar),
        "entradas": entradas,
        "saidas": saidas,
        "liquido": entradas - saidas,
    }


def para_lancamentos(linhas: Sequence[LinhaRevisao], banco_id) -> list:
    """Lançamentos a gravar: as marcadas, sem as duplicadas e as com erro."""
    return [
        {
            "tipo": l.tipo, "data": l.data, "descricao": l.descricao, "categoria_id": l.categoria_id,
            "valor": l.valor, "forma": l.forma, "banco_id": banco_id,
            "observacao": observacao_lancamento(l.texto_original, l.iof), "chave_externa": l.chave,
        }
        for l in linhas if l.importar and l.situacao in SITUACOES_GRAVAVEIS
    ]


def lembrar_escolhas(originais: Sequence[LinhaRevisao], finais: Sequence[LinhaRevisao]):
    """O que o usuário mudou (categoria/tipo) vira regra, e as outras linhas com a mesma descrição que ficaram
    como estavam herdam a escolha. Duplicadas e com erro são ignoradas.

    Devolve (linhas finais com a herança, {(descrição normalizada, é entrada): {"categoria_id", "tipo"}}).
    O campo que não mudou fica None na regra (não congela o que o usuário não escolheu); com mudanças
    diferentes para a mesma descrição, a última vence na regra e cada linha mantém a sua."""
    originais = {l.indice: l for l in originais}
    regras = {}
    for l in finais:
        o = originais[l.indice]
        descricao = normalizar(l.descricao)
        if l.situacao not in SITUACOES_GRAVAVEIS or not descricao:
            continue
        categoria = l.categoria_id if l.categoria_id != o.categoria_id else None
        tipo = l.tipo if (not l.entrada and l.tipo != o.tipo) else None
        if categoria is None and tipo is None:
            continue
        regra = regras.setdefault((descricao, l.entrada), {"categoria_id": None, "tipo": None})
        if categoria is not None:
            regra["categoria_id"] = categoria
        if tipo is not None:
            regra["tipo"] = tipo
    novas = []
    for l in finais:
        o = originais[l.indice]
        regra = regras.get((normalizar(l.descricao), l.entrada))
        if regra and l.situacao in SITUACOES_GRAVAVEIS:
            if regra["categoria_id"] is not None and l.categoria_id == o.categoria_id:
                l = replace(l, categoria_id=regra["categoria_id"])
            if regra["tipo"] is not None and not l.entrada and l.tipo == o.tipo:
                l = replace(l, tipo=regra["tipo"])
        novas.append(l)
    return novas, regras
