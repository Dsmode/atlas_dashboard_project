"""Exportação e importação das Metas Pessoais (metas, tarefas e categorias) em JSON.

O arquivo não leva `id`, porque o auto-incremento não vale entre bancos. Meta duplicada é a de mesmo título
(sem diferenciar caixa e acento) e mesmo prazo; categoria duplicada é a de mesmo nome. O arquivo é tratado
como dado não confiável: tudo passa por `ler_arquivo`, que valida e normaliza antes de gravar."""

import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from database.arquivos import TAMANHO_MAX, ArquivoInvalido
from database.connection import get_cursor
from database.cores import cor_valida
from database.dinheiro import VALOR_MAX, fmt_brl
from database.metas import repo
from database.metas.modelo import (
    CAMPOS_PROGRESSO,
    CATEGORIA_NOME_MAX,
    DESCRICAO_MAX,
    PRIORIDADES,
    STATUS,
    TAREFA_MAX,
    TIPOS_NOME,
    TITULO_MAX,
    UNIDADE_MAX,
)
from database.metas.progresso import OBJETIVOS, TIPOS, fmt_qtd, validar
from database.texto import normalizar

FORMATO = "atlas-metas"
VERSAO = 2

def chave_meta(meta):
    return normalizar(meta["titulo"]), meta["prazo"]


def _data(d):
    return d.isoformat(timespec="seconds") if isinstance(d, datetime) else (d.isoformat() if d else None)


def _dinheiro(valor):
    """Texto ("1200.00"), para o JSON não perder precisão."""
    return None if valor is None else str(Decimal(valor).quantize(Decimal("0.01")))


def carregar_atuais():
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


def _decimal(valor, rotulo):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        raise ArquivoInvalido(f"{rotulo}: era esperado um número.")
    try:
        numero = Decimal(str(valor).strip())
    except InvalidOperation:
        raise ArquivoInvalido(f"{rotulo}: número inválido ({str(valor)[:30]!r}).") from None
    if not numero.is_finite() or abs(numero) > VALOR_MAX:
        raise ArquivoInvalido(f"{rotulo}: valor grande demais.")
    return numero.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _progresso(m, r):
    """Progresso da meta do arquivo, já validado. Metas sem tipo (arquivos v1) são de tarefas."""
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


def _abrir_documento(dados):
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
    return doc


def _ler_tarefa(t, rotulo):
    t = _objeto(t, rotulo)
    return {
        "descricao": _texto(t.get("descricao"), f"{rotulo} (descrição)", TAREFA_MAX, True),
        "prazo": _quando(t.get("prazo"), f"{rotulo} (prazo)", True),
        "concluida": t.get("concluida") is True,
        "data_criacao": _quando(t.get("data_criacao"), f"{rotulo} (data de criação)", False),
        "data_conclusao": _quando(t.get("data_conclusao"), f"{rotulo} (data de conclusão)", False),
    }


def _ler_meta(m, rotulo, registrar_categoria):
    m = _objeto(m, rotulo)
    meta = {
        "titulo": _texto(m.get("titulo"), f"{rotulo} (título)", TITULO_MAX, True),
        "descricao": _texto(m.get("descricao"), f"{rotulo} (descrição)", DESCRICAO_MAX),
        "prioridade": _opcao(m.get("prioridade"), PRIORIDADES, "media", f"{rotulo} (prioridade)"),
        "prazo": _quando(m.get("prazo"), f"{rotulo} (prazo)", True),
        "status": _opcao(m.get("status"), STATUS, "ativa", f"{rotulo} (status)"),
        "data_criacao": _quando(m.get("data_criacao"), f"{rotulo} (data de criação)", False),
        "data_conclusao": _quando(m.get("data_conclusao"), f"{rotulo} (data de conclusão)", False),
        "categorias": [], "tarefas": [], **_progresso(m, rotulo),
    }
    nomes = set()
    for nome in _lista(m.get("categorias"), f"{rotulo} (categorias)"):
        nome = _texto(nome, f"{rotulo} (categoria)", CATEGORIA_NOME_MAX, True)
        if normalizar(nome) not in nomes:
            nomes.add(normalizar(nome))
            meta["categorias"].append(registrar_categoria(nome))
    # Metas de quantidade ou valor não têm checklist: as tarefas do arquivo são ignoradas.
    tarefas_arquivo = _lista(m.get("tarefas"), f"{rotulo} (tarefas)") if meta["tipo_progresso"] == "tarefas" else []
    meta["tarefas"] = [_ler_tarefa(t, f"{rotulo}, tarefa {j}") for j, t in enumerate(tarefas_arquivo, 1)]
    return meta


def ler_arquivo(dados):
    """Valida e normaliza o conteúdo (bytes). Devolve {metas, categorias, repetidas}, onde `repetidas` conta as
    metas que repetem título e prazo de outra do próprio arquivo (só a primeira fica). Levanta
    ArquivoInvalido com o motivo; nada é gravado aqui."""
    doc = _abrir_documento(dados)
    categorias = {}

    def registrar(nome, cor=None):
        norm = normalizar(nome)
        if norm not in categorias:
            categorias[norm] = {"nome": nome, "cor": cor_valida(cor)}
        return nome

    for i, c in enumerate(_lista(doc.get("categorias"), "Categorias"), 1):
        c = _objeto(c, f"Categoria {i}")
        registrar(_texto(c.get("nome"), f"Categoria {i} (nome)", CATEGORIA_NOME_MAX, True), c.get("cor"))

    metas, vistas, repetidas = [], set(), 0
    for i, m in enumerate(_lista(doc.get("metas"), "Metas"), 1):
        meta = _ler_meta(m, f"Meta {i}", registrar)
        chave = chave_meta(meta)
        if chave in vistas:
            repetidas += 1
            continue
        vistas.add(chave)
        metas.append(meta)
    return {"metas": metas, "categorias": list(categorias.values()), "repetidas": repetidas}


def _assinatura(meta):
    """Tudo que define a meta na comparação, exceto as datas de criação e de conclusão."""
    return (
        meta["titulo"].strip(), (meta["descricao"] or "").strip(), meta["prioridade"], meta["prazo"], meta["status"],
        frozenset(normalizar(n) for n in meta["categorias"]),
        tuple(meta[campo] for campo in CAMPOS_PROGRESSO),
        _tarefas(meta),
    )


def _tarefas(meta):
    return tuple((t["descricao"].strip(), t["prazo"], bool(t["concluida"])) for t in meta["tarefas"])


def _resumo_tarefas(meta):
    total = len(meta["tarefas"])
    feitas = sum(1 for t in meta["tarefas"] if t["concluida"])
    return f"{total} tarefa(s), {feitas} concluída(s)"


def _texto_progresso(meta):
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
        if _tarefas(atual) != _tarefas(importada):
            saida.append(("Tarefas", _resumo_tarefas(atual), _resumo_tarefas(importada)))
    elif _texto_progresso(atual) != _texto_progresso(importada):
        saida.append(("Progresso", _texto_progresso(atual), _texto_progresso(importada)))
    return saida


def planejar_mesclagem(arquivo, metas_atuais, categorias_atuais):
    """Compara o arquivo com o banco sem gravar nada. Devolve `novas` (metas sem par), `identicas` (já existem
    iguais e ficam como estão), `conflitos` (mesma chave, conteúdo diferente: atual, importada e
    diferencas), `categorias_novas` e `categorias_conflito` (mesmo nome, cor diferente)."""
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


def _sincronizar_categorias(cur, categorias, trocar_cor):
    cur.execute("SELECT id, nome FROM categorias_meta")
    ids = {normalizar(linha["nome"]): linha["id"] for linha in cur.fetchall()}
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
    """Grava a mesclagem numa transação: se algo falhar, nada muda.

    `substituir` traz as posições de `plano["conflitos"]` em que a versão importada vence; as outras ficam
    como estão. `trocar_cores` traz os nomes de `categorias_conflito` em que a cor importada vence.
    Devolve {novas, substituidas, mantidas, identicas}."""
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
    """Apaga metas, tarefas e categorias e grava as do arquivo, tudo numa transação. As tarefas e as ligações com
    categorias saem em cascata."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM metas")
        cur.execute("DELETE FROM categorias_meta")
        ids = _sincronizar_categorias(cur, arquivo["categorias"], ())
        for meta in arquivo["metas"]:
            _inserir_meta(cur, meta, ids)
    return {"metas": len(arquivo["metas"])}


def apagar_tudo():
    with get_cursor() as cur:
        cur.execute("DELETE FROM metas")
        cur.execute("DELETE FROM categorias_meta")
