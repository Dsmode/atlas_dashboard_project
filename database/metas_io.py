"""Exportação e importação do módulo Metas Pessoais (metas, tarefas e categorias) em JSON.

O arquivo não leva `id`: eles são auto-incrementais e não valem entre bancos. Metas duplicadas são as de
mesmo título (sem diferenciar caixa e acentos) e mesmo prazo; categorias, as de mesmo nome. O arquivo é
tratado como dado não confiável: tudo passa por `ler_arquivo`, que valida e normaliza antes de gravar.
"""
import json
import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from database import metas_repo as repo
from database.connection import get_cursor
from database.metas_progresso import LIMITE, OBJETIVOS, TIPOS, fmt_brl, fmt_qtd, validar

FORMATO = "atlas-metas"
VERSAO = 2
TAMANHO_MAX = 10 * 1024 * 1024  # bytes

PRIORIDADES = {"baixa": "Baixa", "media": "Média", "alta": "Alta"}
STATUS = {"ativa": "Ativa", "concluida": "Concluída", "arquivada": "Arquivada"}
TIPOS_NOME = {"tarefas": "Tarefas", "quantidade": "Quantidade", "valor": "Valor"}
CAMPOS_PROGRESSO = ("tipo_progresso", "objetivo", "unidade", "valor_inicial", "valor_alvo", "valor_atual")
UNIDADE_MAX = 30
COR_PADRAO = "#b44cff"

TITULO_MAX = 150
DESCRICAO_MAX = 16000
TAREFA_MAX = 255
CATEGORIA_MAX = 30


class ArquivoInvalido(Exception):
    """O arquivo não é um export válido; a mensagem diz o motivo, em português."""


def normalizar(texto):
    """Minúsculas e sem acentos (a mesma regra da busca, e a do collation das categorias no banco)."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold().strip()


def chave_meta(meta):
    return normalizar(meta["titulo"]), meta["prazo"]


# ---------- exportar ----------

def _data(d):
    return d.isoformat(timespec="seconds") if isinstance(d, datetime) else (d.isoformat() if d else None)


def _dinheiro(valor):
    """Valor decimal como texto ("1200.00"), para o JSON não perder precisão."""
    return None if valor is None else str(Decimal(valor).quantize(Decimal("0.01")))


def carregar_atuais():
    """Metas e categorias do banco no mesmo formato do arquivo lido (as metas trazem também o `id`)."""
    tarefas = {}
    for t in repo.listar_tarefas():
        tarefas.setdefault(t["meta_id"], []).append({
            "descricao": t["descricao"], "prazo": t["prazo"], "concluida": bool(t["concluida"]),
            "data_conclusao": t["data_conclusao"], "data_criacao": t["data_criacao"],
        })
    metas = [
        {
            "id": m["id"], "titulo": m["titulo"], "descricao": m["descricao"] or None,
            "prioridade": m["prioridade"], "prazo": m["prazo"], "status": m["status"],
            "data_criacao": m["data_criacao"], "data_conclusao": m["data_conclusao"],
            "categorias": [c["nome"] for c in m["categorias"]], "tarefas": tarefas.get(m["id"], []),
            **{campo: m[campo] for campo in CAMPOS_PROGRESSO},
        }
        for m in repo.listar_metas()
    ]
    return metas, repo.listar_categorias()


def contagens(metas, categorias):
    return {
        "metas": len(metas),
        "tarefas": sum(len(m["tarefas"]) for m in metas),
        "categorias": len(categorias),
    }


def exportar_json(agora=None):
    """Bytes do arquivo com tudo do módulo e as contagens (metas, tarefas, categorias)."""
    metas, categorias = carregar_atuais()
    documento = {
        "formato": FORMATO,
        "versao": VERSAO,
        "exportado_em": _data(agora or datetime.now()),
        "categorias": [{"nome": c["nome"], "cor": c["cor"]} for c in categorias],
        "metas": [
            {
                "titulo": m["titulo"], "descricao": m["descricao"], "prioridade": m["prioridade"],
                "prazo": _data(m["prazo"]), "status": m["status"],
                "data_criacao": _data(m["data_criacao"]), "data_conclusao": _data(m["data_conclusao"]),
                "categorias": m["categorias"],
                "tipo_progresso": m["tipo_progresso"], "objetivo": m["objetivo"], "unidade": m["unidade"],
                "valor_inicial": _dinheiro(m["valor_inicial"]), "valor_alvo": _dinheiro(m["valor_alvo"]),
                "valor_atual": _dinheiro(m["valor_atual"]),
                "tarefas": [
                    {
                        "descricao": t["descricao"], "prazo": _data(t["prazo"]), "concluida": t["concluida"],
                        "data_criacao": _data(t["data_criacao"]), "data_conclusao": _data(t["data_conclusao"]),
                    }
                    for t in m["tarefas"]
                ],
            }
            for m in metas
        ],
    }
    dados = json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")
    return dados, contagens(metas, categorias)


# ---------- ler e validar o arquivo ----------

def _texto(valor, rotulo, maximo, obrigatorio=False):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obrigatorio:
            raise ArquivoInvalido(f"{rotulo}: campo obrigatório vazio.")
        return None
    if not isinstance(valor, str):
        raise ArquivoInvalido(f"{rotulo}: era esperado um texto.")
    valor = valor.strip()
    if len(valor) > maximo:
        raise ArquivoInvalido(f"{rotulo}: texto maior que {maximo} caracteres.")
    return valor


def _quando(valor, rotulo, so_data):
    if valor in (None, ""):
        return None
    try:
        if not isinstance(valor, str):
            raise ValueError
        if so_data:
            return date.fromisoformat(valor[:10])
        return datetime.fromisoformat(valor).replace(tzinfo=None, microsecond=0)
    except ValueError:
        raise ArquivoInvalido(f"{rotulo}: data inválida ({str(valor)[:30]!r}).") from None


def _opcao(valor, validos, padrao, rotulo):
    if valor is None:
        return padrao
    if valor not in validos:
        raise ArquivoInvalido(f"{rotulo}: valor inválido ({str(valor)[:30]!r}).")
    return valor


def cor_valida(valor):
    return valor.lower() if isinstance(valor, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", valor) else COR_PADRAO


def _decimal(valor, rotulo):
    """Número do arquivo (inteiro, decimal ou texto numérico) com duas casas; vazio vira None."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        raise ArquivoInvalido(f"{rotulo}: era esperado um número.")
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ArquivoInvalido(f"{rotulo}: número inválido ({str(valor)[:30]!r}).") from None
    if not numero.is_finite() or abs(numero) > LIMITE:
        raise ArquivoInvalido(f"{rotulo}: valor grande demais.")
    return numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _progresso(m, r):
    """Campos de progresso da meta do arquivo, já validados; metas sem tipo (v1) são de tarefas."""
    tipo = _opcao(m.get("tipo_progresso"), TIPOS, "tarefas", f"{r} (tipo de progresso)")
    if tipo == "tarefas":
        return {"tipo_progresso": tipo, "objetivo": "aumentar", "unidade": None,
                "valor_inicial": None, "valor_alvo": None, "valor_atual": None}
    objetivo = _opcao(m.get("objetivo"), OBJETIVOS, "aumentar", f"{r} (objetivo)")
    unidade = _texto(m.get("unidade"), f"{r} (unidade)", UNIDADE_MAX) if tipo == "quantidade" else None
    inicial = _decimal(m.get("valor_inicial"), f"{r} (valor inicial)") if objetivo == "reduzir" else None
    alvo = _decimal(m.get("valor_alvo"), f"{r} (alvo)")
    atual = _decimal(m.get("valor_atual"), f"{r} (valor atual)")
    if atual is None:
        atual = inicial if objetivo == "reduzir" else Decimal("0.00")
    erro = validar(tipo, objetivo, alvo, inicial, atual)
    if erro:
        raise ArquivoInvalido(f"{r} (progresso): {erro}")
    return {"tipo_progresso": tipo, "objetivo": objetivo, "unidade": unidade,
            "valor_inicial": inicial, "valor_alvo": alvo, "valor_atual": atual}


def _lista(valor, rotulo):
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ArquivoInvalido(f"{rotulo}: era esperada uma lista.")
    return valor


def _objeto(valor, rotulo):
    if not isinstance(valor, dict):
        raise ArquivoInvalido(f"{rotulo}: formato inesperado.")
    return valor


def ler_arquivo(dados):
    """Valida e normaliza o conteúdo (bytes). Devolve {"metas", "categorias", "repetidas"}.

    `repetidas` conta as metas que repetem título e prazo de outra do próprio arquivo (só a primeira fica).
    Levanta ArquivoInvalido com o motivo se algo estiver errado; nada é gravado aqui."""
    if len(dados) > TAMANHO_MAX:
        raise ArquivoInvalido("O arquivo é grande demais (limite de 10 MB).")
    try:
        doc = json.loads(dados.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ArquivoInvalido("Não é um arquivo JSON válido.") from None
    doc = _objeto(doc, "Arquivo")
    if doc.get("formato") != FORMATO:
        raise ArquivoInvalido("Este arquivo não foi exportado pelas Metas Pessoais do ATLAS.")
    versao = doc.get("versao")
    if not isinstance(versao, int) or versao > VERSAO:
        raise ArquivoInvalido("O arquivo é de uma versão mais nova do ATLAS; atualize o sistema para importá-lo.")

    categorias = {}  # nome normalizado -> {"nome", "cor"}

    def registrar(nome, cor=None):
        norm = normalizar(nome)
        if norm not in categorias:
            categorias[norm] = {"nome": nome, "cor": cor_valida(cor)}
        return nome

    for i, c in enumerate(_lista(doc.get("categorias"), "Categorias"), 1):
        c = _objeto(c, f"Categoria {i}")
        registrar(_texto(c.get("nome"), f"Categoria {i} (nome)", CATEGORIA_MAX, True), c.get("cor"))

    metas, vistas, repetidas = [], set(), 0
    for i, m in enumerate(_lista(doc.get("metas"), "Metas"), 1):
        r = f"Meta {i}"
        m = _objeto(m, r)
        meta = {
            "titulo": _texto(m.get("titulo"), f"{r} (título)", TITULO_MAX, True),
            "descricao": _texto(m.get("descricao"), f"{r} (descrição)", DESCRICAO_MAX),
            "prioridade": _opcao(m.get("prioridade"), PRIORIDADES, "media", f"{r} (prioridade)"),
            "prazo": _quando(m.get("prazo"), f"{r} (prazo)", True),
            "status": _opcao(m.get("status"), STATUS, "ativa", f"{r} (status)"),
            "data_criacao": _quando(m.get("data_criacao"), f"{r} (data de criação)", False),
            "data_conclusao": _quando(m.get("data_conclusao"), f"{r} (data de conclusão)", False),
            "categorias": [], "tarefas": [], **_progresso(m, r),
        }
        nomes = set()
        for nome in _lista(m.get("categorias"), f"{r} (categorias)"):
            nome = _texto(nome, f"{r} (categoria)", CATEGORIA_MAX, True)
            if normalizar(nome) not in nomes:
                nomes.add(normalizar(nome))
                meta["categorias"].append(registrar(nome))
        # metas de quantidade/valor não têm checklist: tarefas do arquivo são ignoradas
        tarefas_arquivo = _lista(m.get("tarefas"), f"{r} (tarefas)") if meta["tipo_progresso"] == "tarefas" else []
        for j, t in enumerate(tarefas_arquivo, 1):
            rt = f"{r}, tarefa {j}"
            t = _objeto(t, rt)
            meta["tarefas"].append({
                "descricao": _texto(t.get("descricao"), f"{rt} (descrição)", TAREFA_MAX, True),
                "prazo": _quando(t.get("prazo"), f"{rt} (prazo)", True),
                "concluida": t.get("concluida") is True,
                "data_criacao": _quando(t.get("data_criacao"), f"{rt} (data de criação)", False),
                "data_conclusao": _quando(t.get("data_conclusao"), f"{rt} (data de conclusão)", False),
            })
        chave = chave_meta(meta)
        if chave in vistas:
            repetidas += 1
            continue
        vistas.add(chave)
        metas.append(meta)
    return {"metas": metas, "categorias": list(categorias.values()), "repetidas": repetidas}


# ---------- comparar (mesclagem) ----------

def _assinatura(meta):
    """O que define a meta para comparar: tudo menos as datas de criação e conclusão."""
    return (
        meta["titulo"].strip(), (meta["descricao"] or "").strip(), meta["prioridade"], meta["prazo"], meta["status"],
        frozenset(normalizar(n) for n in meta["categorias"]),
        tuple(meta[campo] for campo in CAMPOS_PROGRESSO),
        tuple((t["descricao"].strip(), t["prazo"], bool(t["concluida"])) for t in meta["tarefas"]),
    )


def _resumo_tarefas(meta):
    total = len(meta["tarefas"])
    feitas = sum(1 for t in meta["tarefas"] if t["concluida"])
    return f"{total} tarefa(s), {feitas} concluída(s)"


def _texto_progresso(meta):
    """Progresso em uma frase: "7 de 12 livros", "R$ 1.200,00 de R$ 5.000,00", "3 de 5 tarefas"."""
    if meta["tipo_progresso"] == "tarefas":
        feitas = sum(1 for t in meta["tarefas"] if t["concluida"])
        return f"{feitas} de {len(meta['tarefas'])} tarefas"
    mostrar = fmt_brl if meta["tipo_progresso"] == "valor" else fmt_qtd
    texto = f"{mostrar(meta['valor_atual'])} de {mostrar(meta['valor_alvo'])}"
    if meta["tipo_progresso"] == "quantidade" and meta["unidade"]:
        texto += f" {meta['unidade']}"
    if meta["objetivo"] == "reduzir":
        texto += f" (reduzir a partir de {mostrar(meta['valor_inicial'])})"
    return texto


def diferencas(atual, importada):
    """Lista de (rótulo, valor atual, valor importado) só dos campos que diferem, em texto para exibir."""
    campos = [
        ("Título", lambda m: m["titulo"]),
        ("Descrição", lambda m: m["descricao"] or "sem descrição"),
        ("Prioridade", lambda m: PRIORIDADES[m["prioridade"]]),
        ("Status", lambda m: STATUS[m["status"]]),
        ("Categorias", lambda m: ", ".join(sorted(m["categorias"], key=normalizar)) or "nenhuma"),
    ]
    saida = [(rotulo, f(atual), f(importada)) for rotulo, f in campos if f(atual) != f(importada)]
    tipos = (atual["tipo_progresso"], importada["tipo_progresso"])
    if tipos[0] != tipos[1]:
        saida.append(("Tipo de progresso", TIPOS_NOME[tipos[0]], TIPOS_NOME[tipos[1]]))
    if tipos == ("tarefas", "tarefas"):
        tarefas = lambda m: tuple((t["descricao"].strip(), t["prazo"], bool(t["concluida"])) for t in m["tarefas"])
        if tarefas(atual) != tarefas(importada):
            saida.append(("Tarefas", _resumo_tarefas(atual), _resumo_tarefas(importada)))
    elif _texto_progresso(atual) != _texto_progresso(importada):
        saida.append(("Progresso", _texto_progresso(atual), _texto_progresso(importada)))
    return saida


def planejar_mesclagem(arquivo, metas_atuais, categorias_atuais):
    """Compara o arquivo lido com o banco, sem gravar nada.

    Devolve: `novas` (metas sem par), `identicas` (quantas já existem iguais; ficam como estão),
    `conflitos` (mesma chave, conteúdo diferente: dicts `atual`, `importada`, `diferencas`),
    `categorias_novas` e `categorias_conflito` (mesmo nome com cor diferente: `nome`, `cor_atual`,
    `cor_importada`)."""
    por_chave = {}
    for m in metas_atuais:
        por_chave.setdefault(chave_meta(m), m)
    novas, conflitos, identicas = [], [], 0
    for meta in arquivo["metas"]:
        atual = por_chave.get(chave_meta(meta))
        if atual is None:
            novas.append(meta)
        elif _assinatura(atual) == _assinatura(meta):
            identicas += 1
        else:
            conflitos.append({"atual": atual, "importada": meta, "diferencas": diferencas(atual, meta)})
    existentes = {normalizar(c["nome"]): c for c in categorias_atuais}
    cat_novas, cat_conflito = [], []
    for c in arquivo["categorias"]:
        atual = existentes.get(normalizar(c["nome"]))
        if atual is None:
            cat_novas.append(c)
        elif atual["cor"].lower() != c["cor"]:
            cat_conflito.append({"nome": atual["nome"], "cor_atual": atual["cor"], "cor_importada": c["cor"]})
    return {
        "novas": novas, "identicas": identicas, "conflitos": conflitos,
        "categorias_novas": cat_novas, "categorias_conflito": cat_conflito,
    }


# ---------- gravar ----------

def _sincronizar_categorias(cur, categorias, trocar_cor):
    """Cria as categorias que faltam e troca a cor das de `trocar_cor` (nomes normalizados).
    Devolve {nome normalizado: id}."""
    cur.execute("SELECT id, nome FROM categorias_meta")
    ids = {normalizar(l["nome"]): l["id"] for l in cur.fetchall()}
    for c in categorias:
        norm = normalizar(c["nome"])
        if norm in ids:
            if norm in trocar_cor:
                cur.execute("UPDATE categorias_meta SET cor=%s WHERE id=%s", (c["cor"], ids[norm]))
        else:
            cur.execute("INSERT INTO categorias_meta (nome, cor) VALUES (%s, %s)", (c["nome"], c["cor"]))
            ids[norm] = cur.lastrowid
    return ids


def _gravar_filhos(cur, meta_id, meta, ids_categoria):
    for ordem, t in enumerate(meta["tarefas"]):
        cur.execute(
            "INSERT INTO tarefas_meta (meta_id, descricao, prazo, ordem, concluida, data_conclusao, data_criacao) "
            "VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()))",
            (meta_id, t["descricao"], t["prazo"], ordem, int(t["concluida"]), t["data_conclusao"], t["data_criacao"]),
        )
    for nome in meta["categorias"]:
        cur.execute(
            "INSERT INTO metas_categorias (meta_id, categoria_id) VALUES (%s, %s)",
            (meta_id, ids_categoria[normalizar(nome)]),
        )


def _inserir_meta(cur, meta, ids_categoria):
    cur.execute(
        "INSERT INTO metas (titulo, descricao, prioridade, prazo, status, data_criacao, data_conclusao, "
        "tipo_progresso, objetivo, unidade, valor_inicial, valor_alvo, valor_atual) "
        "VALUES (%s, %s, %s, %s, %s, COALESCE(%s, NOW()), %s, %s, %s, %s, %s, %s, %s)",
        (meta["titulo"], meta["descricao"], meta["prioridade"], meta["prazo"], meta["status"],
         meta["data_criacao"], meta["data_conclusao"], *(meta[campo] for campo in CAMPOS_PROGRESSO)),
    )
    _gravar_filhos(cur, cur.lastrowid, meta, ids_categoria)


def _substituir_meta(cur, meta_id, meta, ids_categoria):
    """A meta do banco passa a ser a importada por inteiro: campos, datas, categorias e tarefas."""
    cur.execute(
        "UPDATE metas SET titulo=%s, descricao=%s, prioridade=%s, prazo=%s, status=%s, "
        "data_criacao=COALESCE(%s, data_criacao), data_conclusao=%s, tipo_progresso=%s, objetivo=%s, "
        "unidade=%s, valor_inicial=%s, valor_alvo=%s, valor_atual=%s WHERE id=%s",
        (meta["titulo"], meta["descricao"], meta["prioridade"], meta["prazo"], meta["status"],
         meta["data_criacao"], meta["data_conclusao"], *(meta[campo] for campo in CAMPOS_PROGRESSO), meta_id),
    )
    cur.execute("DELETE FROM tarefas_meta WHERE meta_id=%s", (meta_id,))
    cur.execute("DELETE FROM metas_categorias WHERE meta_id=%s", (meta_id,))
    _gravar_filhos(cur, meta_id, meta, ids_categoria)


def aplicar_mesclagem(arquivo, plano, substituir=(), trocar_cores=()):
    """Grava a mesclagem numa única transação (se algo falhar, nada muda).

    `substituir`: posições, em `plano["conflitos"]`, das metas cuja versão importada vence; as demais
    ficam como estão. `trocar_cores`: nomes (como em `categorias_conflito`) cuja cor importada vence.
    Devolve {"novas", "substituidas", "mantidas", "identicas"}."""
    substituir = set(substituir)
    trocar = {normalizar(n) for n in trocar_cores}
    with get_cursor() as cur:
        ids = _sincronizar_categorias(cur, arquivo["categorias"], trocar)
        for meta in plano["novas"]:
            _inserir_meta(cur, meta, ids)
        for i, conflito in enumerate(plano["conflitos"]):
            if i in substituir:
                _substituir_meta(cur, conflito["atual"]["id"], conflito["importada"], ids)
    return {
        "novas": len(plano["novas"]), "substituidas": len(substituir),
        "mantidas": len(plano["conflitos"]) - len(substituir), "identicas": plano["identicas"],
    }


def substituir_tudo(arquivo):
    """Apaga metas, tarefas e categorias atuais e grava as do arquivo, numa única transação."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM metas")  # tarefas e ligações com categorias saem em cascata
        cur.execute("DELETE FROM categorias_meta")
        ids = _sincronizar_categorias(cur, arquivo["categorias"], ())
        for meta in arquivo["metas"]:
            _inserir_meta(cur, meta, ids)
    return {"metas": len(arquivo["metas"])}


def apagar_tudo():
    """Apaga metas, tarefas e categorias (usado depois de exportar, se a pessoa pedir)."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM metas")
        cur.execute("DELETE FROM categorias_meta")
