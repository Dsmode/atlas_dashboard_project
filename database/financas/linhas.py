"""Linhas da revisão da importação: monta, resume e converte em lançamentos, sem banco.

Fluxo: `preparar_compras` recorta o intervalo e soma o IOF; a tela consulta as chaves que já existem;
`montar_linhas` resolve descrição, forma, sugestão, ignoradas, duplicadas e erros; o usuário edita;
`para_lancamentos` devolve só o que vai ser gravado."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from database.dinheiro import VALOR_MAX, ZERO, fmt_brl
from database.financas.importacao import (
    Compra,
    chave_externa,
    forma_da_linha,
    fundir_iof,
    limpar_descricao,
    marcar_duplicados,
    motivo_ignorada,
    observacao_lancamento,
    recortar,
)
from database.financas.ofx_leitor import ExtratoOfx
from database.financas.sugestoes import Contexto, sugerir
from database.texto import normalizar

# Quanto o valor importado pode se afastar do previsto quando só a categoria combina.
FOLGA_PREVISAO = Decimal("0.10")
# Descrição menor que isso é curta demais para combinar por estar contida na outra.
DESCRICAO_MINIMA = 3
# Duplicadas e com erro nunca são gravadas.
SITUACOES_GRAVAVEIS = ("novo", "ignorado")


@dataclass
class LinhaRevisao:
    indice: int
    data: date
    descricao: str  # já limpa; o usuário pode editar
    texto_original: str
    valor: Decimal  # positivo (compra mais IOF)
    entrada: bool
    forma: str
    tipo: str  # 'entrada' | 'fixo' | 'variavel'
    categoria_id: int | None
    importar: bool
    situacao: str  # 'novo' | 'duplicado' | 'ignorado' | 'erro'
    motivo: str
    iof: Decimal
    chave: str
    previsao_id: int | None = None  # previsão que esta linha vai preencher; None grava um lançamento novo
    previsao_texto: str = ""


def preparar_compras(extrato: ExtratoOfx, inicio: date, fim: date) -> list:
    return fundir_iof(recortar(extrato.transacoes, inicio, fim))


def montar_linhas(compras: Sequence[Compra], origem: str, meu_nome: str, ctx: Contexto,
                  existentes: Counter) -> list:
    duplicadas = marcar_duplicados([chave_externa(c.principal) for c in compras], existentes)
    linhas = []
    for indice, (compra, duplicada) in enumerate(zip(compras, duplicadas, strict=True)):
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


def _contem(texto, trecho):
    return len(trecho) >= DESCRICAO_MINIMA and f" {trecho} " in f" {texto} "


def _mesma_descricao(linha, previsao):
    nova, antiga = normalizar(linha.descricao), normalizar(previsao["descricao"] or "")
    return bool(nova and antiga) and (nova == antiga or _contem(nova, antiga) or _contem(antiga, nova))


def _mesma_categoria_e_valor(linha, previsao):
    previsto = previsao["valor_previsto"]
    return linha.categoria_id == previsao["categoria_id"] and abs(linha.valor - previsto) <= FOLGA_PREVISAO * previsto


def vincular_previsoes(linhas: Sequence[LinhaRevisao], previsoes: Sequence[dict]) -> list:
    """Sugere, para cada linha nova, uma previsão pendente do mesmo mês e do mesmo grupo (entrada ou gasto).

    Primeiro as que combinam pela descrição, em todas as linhas; depois as de mesma categoria com valor até 10%
    distante. Cada previsão vale para uma linha só, a de valor mais próximo. A linha vinculada assume a
    categoria e o tipo da previsão."""
    linhas = list(linhas)
    livres = {p["id"]: p for p in previsoes}
    for combina in (_mesma_descricao, _mesma_categoria_e_valor):
        pares = sorted(
            (abs(linha.valor - p["valor_previsto"]), posicao, p["id"])
            for posicao, linha in enumerate(linhas)
            if linha.situacao == "novo" and linha.previsao_id is None
            for p in livres.values()
            if (p["tipo"] == "entrada") == linha.entrada
            and (p["data"].year, p["data"].month) == (linha.data.year, linha.data.month) and combina(linha, p)
        )
        for _, posicao, previsao_id in pares:
            if linhas[posicao].previsao_id is not None or previsao_id not in livres:
                continue
            p = livres.pop(previsao_id)
            nome = (p["descricao"] or "").strip() or p["categoria_nome"]
            linhas[posicao] = replace(
                linhas[posicao], previsao_id=previsao_id, categoria_id=p["categoria_id"], tipo=p["tipo"],
                previsao_texto=f"{nome} · {p['data']:%d/%m} · {fmt_brl(p['valor_previsto'])}",
            )
    return linhas


def resumo(linhas: Sequence[LinhaRevisao]) -> dict:
    gravar = [linha for linha in linhas if linha.importar and linha.situacao in SITUACOES_GRAVAVEIS]
    entradas = sum((linha.valor for linha in gravar if linha.entrada), ZERO)
    saidas = sum((linha.valor for linha in gravar if not linha.entrada), ZERO)
    return {
        "novos": sum(1 for linha in linhas if linha.situacao == "novo"),
        "duplicados": sum(1 for linha in linhas if linha.situacao == "duplicado"),
        "ignorados": sum(1 for linha in linhas if linha.situacao == "ignorado"),
        "erros": sum(1 for linha in linhas if linha.situacao == "erro"),
        "a_importar": len(gravar),
        "entradas": entradas,
        "saidas": saidas,
        "liquido": entradas - saidas,
    }


def para_lancamentos(linhas: Sequence[LinhaRevisao], banco_id) -> list:
    lancamentos = []
    for linha in linhas:
        if not linha.importar or linha.situacao not in SITUACOES_GRAVAVEIS:
            continue
        dados = {
            "tipo": linha.tipo, "data": linha.data, "descricao": linha.descricao, "categoria_id": linha.categoria_id,
            "valor": linha.valor, "forma": linha.forma, "banco_id": banco_id,
            "observacao": observacao_lancamento(linha.texto_original, linha.iof), "chave_externa": linha.chave,
        }
        if linha.previsao_id is not None:
            dados["previsao_id"] = linha.previsao_id
        lancamentos.append(dados)
    return lancamentos


def lembrar_escolhas(originais: Sequence[LinhaRevisao], finais: Sequence[LinhaRevisao]):
    """O que o usuário mudou (categoria ou tipo) vira regra, e as outras linhas com a mesma descrição que não
    foram mexidas herdam a escolha. Duplicadas e com erro ficam de fora.

    Devolve as linhas finais com a herança e as regras, indexadas por (descrição normalizada, é entrada).
    O campo que não mudou fica None na regra, para não congelar algo que o usuário não escolheu. Se a mesma
    descrição teve mudanças diferentes, a última vence na regra e cada linha mantém a sua."""
    originais = {linha.indice: linha for linha in originais}
    regras = {}
    for linha in finais:
        o = originais[linha.indice]
        descricao = normalizar(linha.descricao)
        if linha.situacao not in SITUACOES_GRAVAVEIS or not descricao:
            continue
        categoria = linha.categoria_id if linha.categoria_id != o.categoria_id else None
        tipo = linha.tipo if (not linha.entrada and linha.tipo != o.tipo) else None
        if categoria is None and tipo is None:
            continue
        regra = regras.setdefault((descricao, linha.entrada), {"categoria_id": None, "tipo": None})
        if categoria is not None:
            regra["categoria_id"] = categoria
        if tipo is not None:
            regra["tipo"] = tipo
    novas = []
    for linha in finais:
        o = originais[linha.indice]
        regra = regras.get((normalizar(linha.descricao), linha.entrada))
        if regra and linha.situacao in SITUACOES_GRAVAVEIS:
            if regra["categoria_id"] is not None and linha.categoria_id == o.categoria_id:
                linha = replace(linha, categoria_id=regra["categoria_id"])
            if regra["tipo"] is not None and not linha.entrada and linha.tipo == o.tipo:
                linha = replace(linha, tipo=regra["tipo"])
        novas.append(linha)
    return novas, regras
