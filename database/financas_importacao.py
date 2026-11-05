"""Regras puras da importação de extratos: limpeza, linhas ignoradas, IOF, duplicidade e detecção do banco.

Sem banco de dados nem Streamlit: recebe os dados do leitor OFX (`ofx_leitor`) e devolve dados prontos para a
revisão. A sugestão de categoria fica em `financas_sugestoes.py`.
"""
import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from database.financas_calculos import DESCRICAO_MAX, OBSERVACAO_MAX, fmt_brl
from database.ofx_leitor import ExtratoOfx, TransacaoOfx

ZERO = Decimal("0")

# código do banco no OFX (<FID> ou <BANKID>) -> nome do banco padrão
BANCOS_OFX = {"260": "Nubank", "756": "Sicoob", "380": "PicPay", "104": "Caixa"}

_PREFIXO_ADQUIRENTE = re.compile(r"^(?:dm|ebn|pg|mp|pp|ifd|ec)\s?\*\s*", re.I)
_CODIGO_FINAL = re.compile(r"\s+(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{4,10}$")
_NOME_ENTRE_ASPAS = re.compile(r"[\"“”]([^\"“”]+)[\"“”]")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaços colapsados: base de toda comparação de texto."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


# ---------- texto da linha ----------

def limpar_descricao(texto: str) -> str:
    """Tira prefixo de adquirente (Dm*, Ebn*...) e código solto no fim; corta em DESCRICAO_MAX; nunca devolve vazio."""
    original = " ".join((texto or "").split())
    limpo = _PREFIXO_ADQUIRENTE.sub("", original)
    limpo = _CODIGO_FINAL.sub("", limpo).strip()
    return (limpo or original)[:DESCRICAO_MAX].strip()


def forma_da_linha(origem: str, texto: str) -> str:
    if origem == "cartao":
        return "credito"
    return "pix" if "pix" in normalizar(texto) else "debito"


def motivo_ignorada(origem: str, entrada: bool, texto: str, meu_nome: str) -> str:
    """Motivo pelo qual a linha vem desmarcada por padrão; "" se ela deve ser importada."""
    norm = normalizar(texto)
    if origem == "conta" and "pagamento de fatura" in norm:
        return "Pagamento de fatura"
    if origem == "cartao" and entrada and "pagamento recebido" in norm:
        return "Pagamento da fatura anterior"
    nome = normalizar(meu_nome)
    if len(nome) >= 3 and "pix" in norm and nome in norm:
        return "Transferência entre suas contas"
    return ""


# ---------- IOF ----------

@dataclass(frozen=True)
class Compra:
    principal: TransacaoOfx
    valor: Decimal  # positivo: compra + IOF
    iof: Decimal  # parte do valor que é IOF somado (0 se não houve)


def _nome_do_iof(t: TransacaoOfx):
    """Nome entre aspas de uma linha 'IOF de "X"'; None se a linha não é um IOF desse tipo."""
    if t.valor >= 0 or not normalizar(t.texto).startswith("iof de"):
        return None
    achado = _NOME_ENTRE_ASPAS.search(t.texto)
    return normalizar(achado.group(1)) if achado else None


def fundir_iof(transacoes: Sequence[TransacaoOfx]) -> list:
    """Soma cada linha de IOF à compra a que pertence (mesmo FITID; senão mesma data e nome entre aspas)."""
    lista = list(transacoes)
    iofs = {i: nome for i, t in enumerate(lista) if (nome := _nome_do_iof(t)) is not None}
    pai = {}  # índice do IOF -> índice da compra
    for i, nome in iofs.items():
        candidatos = [j for j, c in enumerate(lista) if j not in iofs and c.valor < 0]
        por_fitid = [j for j in candidatos if lista[i].fitid and lista[j].fitid == lista[i].fitid]
        por_nome = [j for j in candidatos
                    if lista[j].data == lista[i].data and normalizar(lista[j].texto) == nome]
        escolhido = (por_fitid or por_nome or [None])[0]
        if escolhido is not None:
            pai[i] = escolhido
    extra = {}
    for i, j in pai.items():
        extra[j] = extra.get(j, ZERO) + abs(lista[i].valor)
    compras = []
    for i, t in enumerate(lista):
        if i in pai:
            continue
        compras.append(Compra(principal=t, valor=abs(t.valor) + extra.get(i, ZERO), iof=extra.get(i, ZERO)))
    return compras


# ---------- duplicidade ----------

def chave_externa(t: TransacaoOfx) -> str:
    """Identifica a linha do banco: o FITID sozinho não serve (o IOF repete o FITID da compra)."""
    base = f"{t.fitid}|{t.data.isoformat()}|{format(t.valor, 'f')}|{normalizar(t.texto)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def marcar_duplicados(chaves: Sequence[str], existentes: Counter) -> list:
    """True para as chaves que já existem, contando por quantidade (dois iguais no arquivo e um no banco: um só)."""
    restante = Counter(existentes)
    marcas = []
    for chave in chaves:
        if restante[chave] > 0:
            restante[chave] -= 1
            marcas.append(True)
        else:
            marcas.append(False)
    return marcas


# ---------- recorte, observação e banco ----------

def recortar(transacoes, inicio, fim) -> list:
    """Linhas com data entre `inicio` e `fim`, inclusive nas duas pontas."""
    return [t for t in transacoes if inicio <= t.data <= fim]


def observacao_lancamento(texto_original: str, iof: Decimal) -> str:
    texto = f"Original: {' '.join((texto_original or '').split())}"
    if iof > 0:
        texto += f" · inclui IOF de {fmt_brl(iof)}"
    return texto[:OBSERVACAO_MAX]


def banco_detectado(extrato: ExtratoOfx, bancos: Sequence[dict]):
    """O banco cadastrado que corresponde ao código do OFX (pelo nome), ou None (não reconhecido ou renomeado)."""
    nome = BANCOS_OFX.get(extrato.codigo_banco)
    if nome is None:
        return None
    return next((b for b in bancos if normalizar(b["nome"]) == normalizar(nome)), None)
