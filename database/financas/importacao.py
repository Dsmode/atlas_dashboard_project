import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from database.dinheiro import ZERO, fmt_brl
from database.financas.calculos import DESCRICAO_MAX, OBSERVACAO_MAX
from database.financas.ofx_leitor import ExtratoOfx, TransacaoOfx
from database.texto import normalizar

# Código do banco no OFX (<FID> ou <BANKID>) para o nome do banco padrão.
BANCOS_OFX = {"260": "Nubank", "756": "Sicoob", "380": "PicPay", "104": "Caixa"}

_PREFIXO_ADQUIRENTE = re.compile(r"^(?:dm|ebn|pg|mp|pp|ifd|ec)\s?\*\s*", re.I)
_CODIGO_FINAL = re.compile(r"\s+(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{4,10}$")
_NOME_ENTRE_ASPAS = re.compile(r"[\"“”]([^\"“”]+)[\"“”]")


def limpar_descricao(texto: str) -> str:
    """Tira o prefixo de adquirente (Dm*, Ebn*) e o código solto no fim, mas nunca devolve vazio."""
    original = " ".join((texto or "").split())
    limpo = _PREFIXO_ADQUIRENTE.sub("", original)
    limpo = _CODIGO_FINAL.sub("", limpo).strip()
    return (limpo or original)[:DESCRICAO_MAX].strip()


def forma_da_linha(origem: str, texto: str) -> str:
    if origem == "cartao":
        return "credito"
    return "pix" if "pix" in normalizar(texto) else "debito"


def motivo_ignorada(origem: str, entrada: bool, texto: str, meu_nome: str) -> str:
    """Por que a linha vem desmarcada, ou "" se deve ser importada: pagamento de fatura, quitação da fatura
    anterior ou Pix entre contas do próprio usuário."""
    norm = normalizar(texto)
    if origem == "conta" and "pagamento de fatura" in norm:
        return "Pagamento de fatura"
    if origem == "cartao" and entrada and "pagamento recebido" in norm:
        return "Pagamento da fatura anterior"
    nome = normalizar(meu_nome)
    if len(nome) >= 3 and "pix" in norm and nome in norm:
        return "Transferência entre suas contas"
    return ""


@dataclass(frozen=True)
class Compra:
    principal: TransacaoOfx
    valor: Decimal  # positivo: compra mais IOF
    iof: Decimal  # parte do valor que é IOF (0 se não houve)


def _nome_do_iof(t: TransacaoOfx):
    if t.valor >= 0 or not normalizar(t.texto).startswith("iof de"):
        return None
    achado = _NOME_ENTRE_ASPAS.search(t.texto)
    return normalizar(achado.group(1)) if achado else None


def fundir_iof(transacoes: Sequence[TransacaoOfx]) -> list:
    """No cartão o IOF vem como linha própria. Ela soma na compra de mesmo FITID ou, sem FITID, de mesma data e
    nome entre aspas."""
    lista = list(transacoes)
    iofs = {i: nome for i, t in enumerate(lista) if (nome := _nome_do_iof(t)) is not None}
    pai = {}
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


def chave_externa(t: TransacaoOfx) -> str:
    """Identifica a linha do banco. O FITID sozinho não serve: o IOF repete o FITID da compra."""
    base = f"{t.fitid}|{t.data.isoformat()}|{format(t.valor, 'f')}|{normalizar(t.texto)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def marcar_duplicados(chaves: Sequence[str], existentes: Counter) -> list:
    """Marca por quantidade: dois lançamentos iguais no arquivo e um no banco marcam só um."""
    restante = Counter(existentes)
    marcas = []
    for chave in chaves:
        if restante[chave] > 0:
            restante[chave] -= 1
            marcas.append(True)
        else:
            marcas.append(False)
    return marcas


def recortar(transacoes, inicio, fim) -> list:
    return [t for t in transacoes if inicio <= t.data <= fim]


def observacao_lancamento(texto_original: str, iof: Decimal) -> str:
    texto = f"Original: {' '.join((texto_original or '').split())}"
    if iof > 0:
        texto += f" · inclui IOF de {fmt_brl(iof)}"
    return texto[:OBSERVACAO_MAX]


def banco_detectado(extrato: ExtratoOfx, bancos: Sequence[dict]):
    """Banco cadastrado que bate com o código do OFX; None se o código é desconhecido ou o banco foi renomeado."""
    nome = BANCOS_OFX.get(extrato.codigo_banco)
    if nome is None:
        return None
    return next((b for b in bancos if normalizar(b["nome"]) == normalizar(nome)), None)
