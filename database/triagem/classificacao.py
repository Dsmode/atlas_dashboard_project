"""Em qual card fixo cada e-mail cai e por quê. Puro e determinístico: mesmas entradas, mesmo resultado.

Ordem (a primeira que casa vence): suspeito > protegido > lixo > revisar. Enviados não entram em card.
As fases seguintes acrescentam bloqueios (antes de tudo) e cards configuráveis (entre protegido e lixo)."""
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

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


def classificar(emails, protegidos):
    """`emails`: dicts com id, remetente_email, remetente_nome, dominio, lido (0/1), categoria,
    tem_cancelamento (bool), spf, dkim, dmarc, spam (bool), enviado (bool).

    Devolve {id: (card, motivo)}. Enviados ficam de fora do resultado."""
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
        else:
            total, lidos = por_remetente[remetente]
            taxa = lidos / total if total else 0
            if e["categoria"] in ("promocoes", "social") and not e["lido"] and e.get("tem_cancelamento"):
                resultado[e["id"]] = (LIXO, "Promoção nunca aberta, com opção de sair")
            elif total >= VOLUME_ALTO and taxa <= LEITURA_BAIXA:
                resultado[e["id"]] = (LIXO, f"Envia muito ({total}) e você lê {taxa:.1%}")
            elif not e["lido"]:
                resultado[e["id"]] = (REVISAR, "Não lido, sem sinal claro")
    return resultado


def resumo_por_card(emails, classificacao):
    """{card: {"emails": n, "remetentes": n, "top": [(remetente, n), ...]}} para os cards fixos e protegidos."""
    contagens = {c: Counter() for c in (*CARDS_FIXOS, PROTEGIDO)}
    for e in emails:
        item = classificacao.get(e["id"])
        if item:
            contagens[item[0]][(e["remetente_email"] or "(sem remetente)").lower()] += 1
    return {
        c: {"emails": sum(cont.values()), "remetentes": len(cont), "top": cont.most_common(3)}
        for c, cont in contagens.items()
    }


def remetentes_do_card(emails, classificacao, card):
    """Linhas para a lista de um card: um remetente por linha, do maior volume para o menor.

    Cada linha: remetente, nome, dominio, emails, lidos (fração), motivo (o mais comum entre os e-mails)."""
    grupos = {}
    for e in emails:
        item = classificacao.get(e["id"])
        if not item or item[0] != card:
            continue
        chave = (e["remetente_email"] or "(sem remetente)").lower()
        g = grupos.setdefault(chave, {"remetente": chave, "nome": e.get("remetente_nome") or "", "dominio": e.get("dominio") or "",
                                      "emails": 0, "lidos": 0, "motivos": Counter()})
        g["emails"] += 1
        g["lidos"] += 1 if e["lido"] else 0
        g["motivos"][item[1]] += 1
    linhas = []
    for g in grupos.values():
        linhas.append({
            "remetente": g["remetente"], "nome": g["nome"], "dominio": g["dominio"], "emails": g["emails"],
            "lidos": g["lidos"] / g["emails"], "motivo": g["motivos"].most_common(1)[0][0],
        })
    return sorted(linhas, key=lambda r: (-r["emails"], r["remetente"]))
