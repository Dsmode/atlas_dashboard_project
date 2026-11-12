"""Regras dos cards configuráveis: critérios E, OU e NÃO. Puro (sem banco nem Streamlit), determinístico e explicável.

Um card casa com um e-mail quando: todos os critérios E casam, pelo menos um critério OU casa (se houver algum) e
nenhum critério NÃO casa. Um card sem nenhum critério E nem OU não casa com nada (evita um card que pega tudo)."""
import unicodedata

OPERADORES = {"e": "E (todos precisam casar)", "ou": "OU (pelo menos um precisa casar)", "nao": "NÃO (nenhum pode casar)"}
CATEGORIAS = {"principal": "Principal", "promocoes": "Promoções", "social": "Social", "atualizacoes": "Atualizações",
              "foruns": "Fóruns"}
# campo -> (rótulo para a tela, valores fixos ou None para texto livre)
CAMPOS = {
    "texto": ("Assunto ou trecho contém", None),
    "assunto": ("Assunto contém", None),
    "remetente": ("Nome ou e-mail do remetente contém", None),
    "email": ("E-mail do remetente é", None),
    "dominio": ("Domínio do remetente é", None),
    "categoria": ("Categoria do Gmail é", CATEGORIAS),
    "leitura": ("Leitura é", {"nao_lido": "Não lido", "lido": "Lido"}),
    "cancelamento": ("Tem opção de cancelar inscrição", {"sim": "Sim", "nao": "Não"}),
}
TAMANHO_MAXIMO_VALOR = 255


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn").lower()


def preparar(e):
    """Campos normalizados de um e-mail, calculados uma vez e reaproveitados por todas as regras."""
    return {
        "texto": sem_acento(f"{e.get('assunto') or ''} {e.get('snippet') or ''}"),
        "assunto": sem_acento(e.get("assunto")),
        "remetente": sem_acento(f"{e.get('remetente_nome') or ''} {e.get('remetente_email') or ''}"),
        "email": (e.get("remetente_email") or "").lower(),
        "dominio": (e.get("dominio") or "").lower(),
        "categoria": e.get("categoria") or "",
        "leitura": "lido" if e.get("lido") else "nao_lido",
        "cancelamento": "sim" if e.get("tem_cancelamento") else "nao",
    }


def normalizar_valor(campo, valor):
    valor = " ".join(str(valor or "").split())[:TAMANHO_MAXIMO_VALOR]
    return sem_acento(valor) if campo in ("texto", "assunto", "remetente") else valor.lower()


def criterio_valido(criterio):
    return (criterio.get("operador") in OPERADORES and criterio.get("campo") in CAMPOS
            and bool(normalizar_valor(criterio["campo"], criterio.get("valor"))))


def _casa_criterio(campo, valor, p):
    if campo in ("texto", "assunto", "remetente"):
        return valor in p[campo]
    if campo == "dominio":
        return p["dominio"] == valor or p["dominio"].endswith("." + valor)
    return p[campo] == valor


def descrever(criterio):
    rotulo, fixos = CAMPOS[criterio["campo"]]
    valor = criterio["valor"]
    return f'{rotulo.lower()} "{fixos.get(valor, valor) if fixos else valor}"'


def validar(criterios):
    """Só os critérios completos entram; devolve (lista limpa, mensagem de erro ou None)."""
    limpos = [{"operador": c["operador"], "campo": c["campo"], "valor": normalizar_valor(c["campo"], c["valor"])}
              for c in criterios if criterio_valido(c)]
    if not any(c["operador"] in ("e", "ou") for c in limpos):
        return limpos, "Adicione pelo menos um critério E ou OU: só com NÃO o card não pegaria nenhum e-mail."
    return limpos, None


def casa(criterios, p):
    """`criterios` já validados (valores normalizados) e `p` um e-mail preparado."""
    obrigatorios = [c for c in criterios if c["operador"] == "e"]
    alternativas = [c for c in criterios if c["operador"] == "ou"]
    proibidos = [c for c in criterios if c["operador"] == "nao"]
    if not obrigatorios and not alternativas:
        return False
    if not all(_casa_criterio(c["campo"], c["valor"], p) for c in obrigatorios):
        return False
    if alternativas and not any(_casa_criterio(c["campo"], c["valor"], p) for c in alternativas):
        return False
    return not any(_casa_criterio(c["campo"], c["valor"], p) for c in proibidos)


def motivos(criterios, p):
    """Por que o e-mail casou: os critérios E e OU que casaram (os NÃO só impedem, não explicam)."""
    return [descrever(c) for c in criterios if c["operador"] in ("e", "ou") and _casa_criterio(c["campo"], c["valor"], p)]


def ids_que_casam(criterios, preparados):
    return {i for i, p in preparados.items() if casa(criterios, p)}


def palavra_que_salva(palavras, p):
    """A primeira palavra que salva presente no assunto ou trecho, ou None. `palavras` já normalizadas."""
    return next((w for w in palavras if w in p["texto"]), None)
