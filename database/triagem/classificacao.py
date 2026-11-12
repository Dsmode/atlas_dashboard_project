"""Em qual card fixo cada e-mail cai e por quê. Puro e determinístico: mesmas entradas, mesmo resultado.

Ordem (a primeira que casa vence): suspeito > protegido > regras dos cards do usuário > lixo > revisar. Quem casa
com uma regra de card do usuário não vai para Lixo nem Revisar (a regra do usuário vale mais que o sinal
automático). Palavras que salvam impedem o Lixo. Enviados não entram em card.
A Fase 4 acrescenta bloqueios (antes de tudo)."""
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from . import regras

SUSPEITO, PROTEGIDO, LIXO, REVISAR = "spam", "protegido", "lixo", "revisar"
CARDS_FIXOS = (LIXO, SUSPEITO, REVISAR)

VOLUME_ALTO = 20       # e-mails de um mesmo remetente a partir dos quais ele conta como "alto volume"
LEITURA_BAIXA = 0.05   # até 5% lidos = "leitura perto de zero"
SEMELHANCA_MINIMA = 0.8
NOME_MINIMO = 6        # nomes de marca curtos demais ("caixa") dão falso alarme no nome de exibição

PROTEGIDOS_PADRAO = (
    "nubank.com.br", "sicoob.com.br", "picpay.com", "caixa.gov.br", "gov.br", "receita.fazenda.gov.br",
    "picpay.com.br", "gupy.io", "linkedin.com", "indeed.com", "infojobs.com.br", "catho.com.br", "vagas.com.br",
)


PALAVRAS_SALVAM_PADRAO = (
    "proposta", "interessado", "interessada", "pedido", "boleto", "entrega", "rastreio", "comprador", "nota fiscal",
    "agendamento",
)


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def normalizar_protegido(valor):
    """Aceita "avisos@nubank.com.br" ou "nubank.com.br". Devolve (tipo, valor) ou None se não for nada útil."""
    valor = (valor or "").strip().lower()
    if not valor or " " in valor:
        return None
    if "@" in valor:
        return ("email", valor) if valor.count("@") == 1 and "." in valor.split("@")[1] else None
    valor = valor.removeprefix("www.")
    return ("dominio", valor) if "." in valor else None


def e_protegido(email, dominio, protegidos):
    """`protegidos` é o conjunto de valores (domínios e e-mails). Subdomínios casam (mail.nubank.com.br)."""
    email, dominio = (email or "").lower(), (dominio or "").lower()
    if email in protegidos:
        return True
    partes = dominio.split(".")
    return any(".".join(partes[i:]) in protegidos for i in range(len(partes) - 1))


def _marcas(protegidos):
    """Nome curto de cada domínio protegido (nubank.com.br -> nubank); gov.br e afins ficam de fora."""
    marcas = {}
    for valor in protegidos:
        if "@" in valor:
            continue
        nome = valor.split(".")[0]
        if len(nome) >= 4 and nome not in ("gov", "receita"):
            marcas[nome] = valor
    return marcas


def _dominio_parecido(dominio, marcas):
    """Domínio com um rótulo quase igual ao de um protegido (nubamk-seguranca.com). Devolve o motivo ou None."""
    rotulos = [r for r in _sem_acento(dominio).replace("-", ".").split(".") if r]
    for marca in marcas:
        for rotulo in rotulos:
            if rotulo != marca and abs(len(rotulo) - len(marca)) <= 1                     and SequenceMatcher(None, rotulo, marca).ratio() >= SEMELHANCA_MINIMA:
                return f"Domínio parecido com {marca} ({rotulo})"
    return None


def _nome_imita(nome_exibido, marcas):
    nome = _sem_acento(nome_exibido)
    return next((f"Nome imita {m}, domínio não oficial" for m in marcas if len(m) >= NOME_MINIMO and m in nome), None)


def _reprovado(e):
    """Alguma verificação (SPF, DKIM, DMARC) falhou de verdade. Verificação ausente não é falha."""
    return any((e.get(m) or "") in ("fail", "softfail") for m in ("spf", "dkim", "dmarc"))


def _forjado(e, protegido):
    """DMARC falhando em domínio qualquer é comum em e-mail legítimo (ferramentas de envio, contas @gmail.com), por
    isso só conta quando o remetente diz ser um protegido. SPF e DKIM falhando juntos conta sempre."""
    if protegido and (e.get("dmarc") or "") == "fail":
        return "Falhou DMARC em remetente protegido (pode ser forjado)"
    if (e.get("spf") or "") == "fail" and (e.get("dkim") or "") == "fail":
        return "Falhou SPF e DKIM (pode ser forjado)"
    return None


def classificar(emails, protegidos, em_cards=frozenset(), salvam=(), preparados=None):
    """`emails`: dicts com id, remetente_email, remetente_nome, dominio, lido (0/1), categoria,
    tem_cancelamento (bool), spf, dkim, dmarc, spam (bool), enviado (bool).
    `em_cards`: ids que casam com alguma regra de card do usuário. `salvam`: palavras que salvam (normalizadas).
    `preparados`: {id: regras.preparar(e)} (opcional; calculado na hora se faltar).

    Devolve {id: (card, motivo)}. Enviados e e-mails resolvidos por regra do usuário ficam de fora do resultado
    (menos suspeitos e protegidos, que mantêm o card fixo)."""
    protegidos = {p.lower() for p in protegidos}
    marcas = _marcas(protegidos)

    por_remetente = defaultdict(lambda: [0, 0])  # total, lidos (só e-mails recebidos)
    for e in emails:
        if not e.get("enviado"):
            conta = por_remetente[(e["remetente_email"] or "").lower()]
            conta[0] += 1
            conta[1] += 1 if e["lido"] else 0

    cache_dominio = {}
    resultado = {}
    for e in emails:
        if e.get("enviado"):
            continue
        remetente = (e["remetente_email"] or "").lower()
        protegido = e_protegido(remetente, e.get("dominio"), protegidos)
        motivo = _forjado(e, protegido)  # um protegido forjado continua sendo golpe: a verificação vem antes da lista
        if not motivo and not protegido:
            dominio = e.get("dominio")
            if dominio not in cache_dominio:
                cache_dominio[dominio] = _dominio_parecido(dominio, marcas)
            motivo = cache_dominio[dominio]
            if not motivo and _reprovado(e):  # nome de marca sem falha de autenticação costuma ser fornecedor ou afiliada
                motivo = _nome_imita(e.get("remetente_nome"), marcas)
            motivo = motivo or ("Marcado como spam pelo Gmail" if e.get("spam") else None)

        if motivo:
            resultado[e["id"]] = (SUSPEITO, motivo)
        elif protegido:
            resultado[e["id"]] = (PROTEGIDO, "Remetente protegido")
        elif e["id"] not in em_cards:
            total, lidos = por_remetente[remetente]
            taxa = lidos / total if total else 0
            lixo = None
            if e["categoria"] in ("promocoes", "social") and not e["lido"] and e.get("tem_cancelamento"):
                lixo = "Promoção nunca aberta, com opção de sair"
            elif total >= VOLUME_ALTO and taxa <= LEITURA_BAIXA:
                lixo = f"Envia muito ({total}) e você lê {taxa:.1%}"
            salvou = None
            if lixo and salvam:
                p = (preparados or {}).get(e["id"]) or regras.preparar(e)
                salvou = regras.palavra_que_salva(salvam, p)
            if salvou:
                if not e["lido"]:
                    resultado[e["id"]] = (REVISAR, f'Iria para o Lixo, mas tem a palavra "{salvou}"')
            elif lixo:
                resultado[e["id"]] = (LIXO, lixo)
            elif not e["lido"]:
                resultado[e["id"]] = (REVISAR, "Não lido, sem sinal claro")
    return resultado


def membros_dos_cards(cards, preparados, classificacao):
    """{id do card: ids dos e-mails}. Um e-mail pode estar em vários cards. Suspeitos ficam de fora: o bloqueio
    vem antes das regras. Protegidos entram (a proteção só impede mover em lote, não pertencer a um card)."""
    return {
        card["id"]: {
            i for i in regras.ids_que_casam(card["criterios"], preparados) if classificacao.get(i, ("",))[0] != SUSPEITO
        }
        for card in cards
    }


def ids_que_casam_com_algum(cards, preparados):
    achados = set()
    for card in cards:
        achados |= regras.ids_que_casam(card["criterios"], preparados)
    return achados


def resumo_de_ids(emails, ids):
    """{"emails": n, "remetentes": n, "top": [(remetente, n), ...]} para um conjunto de e-mails."""
    cont = Counter((e["remetente_email"] or "(sem remetente)").lower() for e in emails if e["id"] in ids)
    return {"emails": sum(cont.values()), "remetentes": len(cont), "top": cont.most_common(3)}


def resumo_por_card(emails, classificacao):
    """{card fixo: resumo_de_ids} para Lixo, Spam e suspeitos, Revisar e protegidos."""
    por_card = defaultdict(set)
    for i, (card, _) in classificacao.items():
        por_card[card].add(i)
    return {c: resumo_de_ids(emails, por_card[c]) for c in (*CARDS_FIXOS, PROTEGIDO)}


def remetentes_de(emails, ids, motivo_de):
    """Linhas para a lista de um card: um remetente por linha, do maior volume para o menor.

    `motivo_de(e)` devolve o motivo de cada e-mail. Cada linha: remetente, nome, dominio, emails, lidos (fração),
    motivo (o mais comum entre os e-mails do remetente)."""
    grupos = {}
    for e in emails:
        if e["id"] not in ids:
            continue
        chave = (e["remetente_email"] or "(sem remetente)").lower()
        g = grupos.setdefault(chave, {"remetente": chave, "nome": e.get("remetente_nome") or "",
                                      "dominio": e.get("dominio") or "", "emails": 0, "lidos": 0, "motivos": Counter()})
        g["emails"] += 1
        g["lidos"] += 1 if e["lido"] else 0
        g["motivos"][motivo_de(e)] += 1
    linhas = [
        {"remetente": g["remetente"], "nome": g["nome"], "dominio": g["dominio"], "emails": g["emails"],
         "lidos": g["lidos"] / g["emails"], "motivo": g["motivos"].most_common(1)[0][0]}
        for g in grupos.values()
    ]
    return sorted(linhas, key=lambda r: (-r["emails"], r["remetente"]))


def remetentes_do_card(emails, classificacao, card):
    ids = {i for i, (c, _) in classificacao.items() if c == card}
    return remetentes_de(emails, ids, lambda e: classificacao[e["id"]][1])
