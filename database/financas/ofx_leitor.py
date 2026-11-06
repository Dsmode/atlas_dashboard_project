"""Leitor de OFX (extrato de conta e fatura de cartão), sem banco nem Streamlit.

O OFX dos bancos é SGML com tags que não fecham, então a leitura usa expressões regulares. Isso também
cobre o OFX 2.x (XML) e evita expandir entidades externas. As mensagens de ArquivoInvalido são para o
usuário."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import unescape

from database.arquivos import TAMANHO_MAX, ArquivoInvalido
from database.dinheiro import CENTAVO


@dataclass(frozen=True)
class TransacaoOfx:
    fitid: str
    data: date
    valor: Decimal  # com sinal: saída é negativa
    texto: str  # MEMO, senão NAME, senão ""


@dataclass(frozen=True)
class ExtratoOfx:
    origem: str  # 'conta' | 'cartao'
    instituicao: str
    codigo_banco: str  # <FID>, senão <BANKID>, sem zeros à esquerda; "" se faltar
    inicio: date | None
    fim: date | None
    transacoes: tuple


_CHARSET = re.compile(rb"(?:CHARSET|ENCODING)\s*:\s*([A-Za-z0-9\-]+)", re.I)


def _decodificar(conteudo):
    """O cabeçalho (CHARSET 1252 ou ENCODING) decide. Sem ele, tenta UTF-8 e cai para Windows-1252."""
    cabecalho = conteudo[:800]
    for valor in _CHARSET.findall(cabecalho):
        if valor.upper() in (b"1252", b"WINDOWS-1252", b"CP1252"):
            return conteudo.decode("cp1252", errors="replace")
    try:
        return conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252", errors="replace")


def _tag(bloco, nome):
    achado = re.search(rf"<{nome}>\s*([^<\r\n]*)", bloco, re.I)
    return achado.group(1).strip() if achado else ""


def _data(texto, onde, obrigatoria=True):
    digitos = (texto or "")[:8]
    try:
        if not re.fullmatch(r"\d{8}", digitos):
            raise ValueError
        return date(int(digitos[:4]), int(digitos[4:6]), int(digitos[6:8]))
    except ValueError:
        if obrigatoria:
            raise ArquivoInvalido(f"Data inválida no arquivo ({onde}).") from None
        return None


def _valor(texto):
    bruto = (texto or "").strip().replace(" ", "")
    if "," in bruto and "." in bruto:
        # Com ponto e vírgula juntos, o último é o separador decimal e o outro é de milhar.
        if bruto.rfind(",") > bruto.rfind("."):
            bruto = bruto.replace(".", "").replace(",", ".")
        else:
            bruto = bruto.replace(",", "")
    else:
        bruto = bruto.replace(",", ".")
    try:
        valor = Decimal(bruto)
    except InvalidOperation:
        raise ArquivoInvalido(f"Valor inválido no arquivo: “{texto[:30]}”.") from None
    if not valor.is_finite():
        raise ArquivoInvalido(f"Valor inválido no arquivo: “{texto[:30]}”.")
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _texto(bloco):
    bruto = _tag(bloco, "MEMO") or _tag(bloco, "NAME")
    return " ".join(unescape(bruto).split())


def _transacoes(corpo):
    pedacos = re.split(r"<STMTTRN>", corpo, flags=re.I)[1:]
    saida = []
    for pedaco in pedacos:
        bloco = re.split(r"</STMTTRN>|</BANKTRANLIST>", pedaco, maxsplit=1, flags=re.I)[0]
        saida.append(TransacaoOfx(
            fitid=_tag(bloco, "FITID"),
            data=_data(_tag(bloco, "DTPOSTED"), "DTPOSTED"),
            valor=_valor(_tag(bloco, "TRNAMT")),
            texto=_texto(bloco),
        ))
    return tuple(saida)


def ler_ofx(conteudo: bytes) -> ExtratoOfx:
    if not conteudo or not conteudo.strip():
        raise ArquivoInvalido("O arquivo está vazio.")
    if len(conteudo) > TAMANHO_MAX:
        raise ArquivoInvalido("O arquivo é grande demais (limite de 10 MB).")
    texto = _decodificar(conteudo)
    if not re.search(r"<OFX[\s>]", texto, re.I):
        raise ArquivoInvalido("O arquivo não parece ser um OFX. Exporte o extrato do banco no formato OFX.")
    if re.search(r"<CCSTMTRS[\s>]", texto, re.I):
        origem = "cartao"
    elif re.search(r"<STMTRS[\s>]", texto, re.I):
        origem = "conta"
    else:
        raise ArquivoInvalido("Não encontrei um extrato de conta nem uma fatura de cartão neste arquivo.")
    moeda = _tag(texto, "CURDEF").upper()
    if moeda and moeda != "BRL":
        raise ArquivoInvalido(f"Só extratos em reais (BRL) são suportados; este está em {moeda}.")
    transacoes = _transacoes(texto)
    if not transacoes:
        raise ArquivoInvalido("O arquivo não tem nenhuma transação.")
    codigo = (_tag(texto, "FID") or _tag(texto, "BANKID")).lstrip("0")
    return ExtratoOfx(
        origem=origem,
        instituicao=" ".join(unescape(_tag(texto, "ORG")).split()),
        codigo_banco=codigo,
        inicio=_data(_tag(texto, "DTSTART"), "DTSTART", obrigatoria=False),
        fim=_data(_tag(texto, "DTEND"), "DTEND", obrigatoria=False),
        transacoes=transacoes,
    )
