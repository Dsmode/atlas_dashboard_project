from collections import Counter
from decimal import Decimal

from database.connection import duplicidade, get_cursor
from database.dinheiro import ZERO
from database.financas.calculos import grupo_categoria
from database.financas.padroes import COR_OUTROS, NOME_OUTROS
from database.texto import normalizar


class NomeDuplicado(Exception):
    pass


class CategoriaProtegida(Exception):
    pass


class CategoriaIncompativel(ValueError):
    """Categoria de outro grupo (entrada ou gasto) ou que já não existe."""


def listar_categorias(tipo=None):
    """Categorias com `em_uso` (quantos lançamentos usam cada uma). "Outros" vem por último em cada tipo."""
    filtro, params = ("WHERE c.tipo = %s", (tipo,)) if tipo else ("", ())
    with get_cursor() as cur:
        cur.execute(
            "SELECT c.id, c.tipo, c.nome, c.cor, c.protegida, COUNT(l.id) AS em_uso FROM fin_categorias c "
            f"LEFT JOIN fin_lancamentos l ON l.categoria_id = c.id {filtro} "
            "GROUP BY c.id ORDER BY c.tipo, c.protegida, c.nome",
            params,
        )
        return cur.fetchall()


def criar_categoria(tipo, nome, cor):
    with duplicidade(NomeDuplicado, nome), get_cursor() as cur:
        cur.execute("INSERT INTO fin_categorias (tipo, nome, cor) VALUES (%s, %s, %s)", (tipo, nome, cor))
        return cur.lastrowid


def atualizar_categoria(categoria_id, nome, cor):
    with duplicidade(NomeDuplicado, nome), get_cursor() as cur:
        cur.execute("UPDATE fin_categorias SET nome=%s, cor=%s WHERE id=%s", (nome, cor, categoria_id))


def excluir_categoria(categoria_id):
    """Move os lançamentos para a "Outros" do mesmo tipo e apaga a categoria. Devolve quantos mudaram."""
    with get_cursor() as cur:
        cur.execute("SELECT tipo, protegida FROM fin_categorias WHERE id=%s", (categoria_id,))
        categoria = cur.fetchone()
        if categoria is None:
            return 0
        if categoria["protegida"]:
            raise CategoriaProtegida()
        cur.execute(
            "SELECT id FROM fin_categorias WHERE tipo=%s AND protegida=1 ORDER BY id LIMIT 1", (categoria["tipo"],),
        )
        outros = cur.fetchone()
        # Banco montado à mão, sem a "Outros" protegida: cria uma (ou protege a que já existir).
        if outros is None:
            cur.execute(
                "INSERT INTO fin_categorias (tipo, nome, cor, protegida) VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE protegida = 1, id = LAST_INSERT_ID(id)",
                (categoria["tipo"], NOME_OUTROS, COR_OUTROS),
            )
            outros = {"id": cur.lastrowid}
        cur.execute("UPDATE fin_lancamentos SET categoria_id=%s WHERE categoria_id=%s", (outros["id"], categoria_id))
        movidos = cur.rowcount
        cur.execute("UPDATE fin_regras SET categoria_id=%s WHERE categoria_id=%s", (outros["id"], categoria_id))
        cur.execute("DELETE FROM fin_categorias WHERE id=%s", (categoria_id,))
        return movidos


def listar_bancos(incluir_ocultos=False):
    filtro = "" if incluir_ocultos else "WHERE b.ativo = 1"
    with get_cursor() as cur:
        cur.execute(
            "SELECT b.id, b.nome, b.sigla, b.cor, b.ativo, COUNT(l.id) AS em_uso FROM fin_bancos b "
            f"LEFT JOIN fin_lancamentos l ON l.banco_id = b.id {filtro} GROUP BY b.id ORDER BY b.nome"
        )
        return cur.fetchall()


def criar_banco(nome, sigla, cor):
    with duplicidade(NomeDuplicado, nome), get_cursor() as cur:
        cur.execute("INSERT INTO fin_bancos (nome, sigla, cor) VALUES (%s, %s, %s)", (nome, sigla, cor))
        return cur.lastrowid


def atualizar_banco(banco_id, nome, sigla, cor):
    with duplicidade(NomeDuplicado, nome), get_cursor() as cur:
        cur.execute(
            "UPDATE fin_bancos SET nome=%s, sigla=%s, cor=%s WHERE id=%s", (nome, sigla, cor, banco_id),
        )


def definir_banco_ativo(banco_id, ativo):
    """Ocultar tira o banco do formulário; os lançamentos antigos continuam mostrando o nome dele."""
    with get_cursor() as cur:
        cur.execute("UPDATE fin_bancos SET ativo=%s WHERE id=%s", (int(bool(ativo)), banco_id))


def excluir_banco(banco_id):
    """Os lançamentos do banco ficam sem banco (FK ON DELETE SET NULL). Devolve quantos eram."""
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM fin_lancamentos WHERE banco_id=%s", (banco_id,))
        afetados = cur.fetchone()["n"]
        cur.execute("DELETE FROM fin_bancos WHERE id=%s", (banco_id,))
        return afetados


def obter_saldo_inicial():
    with get_cursor() as cur:
        cur.execute("SELECT valor FROM fin_config WHERE chave = 'saldo_inicial'")
        linha = cur.fetchone()
    return Decimal(linha["valor"]) if linha else ZERO


def definir_saldo_inicial(valor):
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO fin_config (chave, valor) VALUES ('saldo_inicial', %s) "
            "ON DUPLICATE KEY UPDATE valor = VALUES(valor)",
            (str(Decimal(valor)),),
        )


_SELECT_LANCAMENTOS = (
    "SELECT l.id, l.tipo, l.data, l.descricao, l.categoria_id, l.valor, l.forma, l.banco_id, l.observacao, "
    "c.nome AS categoria_nome, c.cor AS categoria_cor, "
    "b.nome AS banco_nome, b.sigla AS banco_sigla, b.cor AS banco_cor "
    "FROM fin_lancamentos l JOIN fin_categorias c ON c.id = l.categoria_id "
    "LEFT JOIN fin_bancos b ON b.id = l.banco_id "
)


def listar_lancamentos(inicio, fim, tipo=None):
    filtro, params = ("AND l.tipo = %s", (inicio, fim, tipo)) if tipo else ("", (inicio, fim))
    with get_cursor() as cur:
        cur.execute(
            _SELECT_LANCAMENTOS + f"WHERE l.data BETWEEN %s AND %s {filtro} ORDER BY l.data DESC, l.id DESC",
            params,
        )
        return cur.fetchall()


def _conferir_categoria(cur, dados):
    """A tela já filtra as categorias pelo tipo; esta é a última barreira antes de gravar."""
    cur.execute("SELECT tipo FROM fin_categorias WHERE id = %s", (dados["categoria_id"],))
    categoria = cur.fetchone()
    if categoria is None or categoria["tipo"] != grupo_categoria(dados["tipo"]):
        raise CategoriaIncompativel(dados["categoria_id"])


def _valores(dados):
    banco_id = None if dados["forma"] == "dinheiro" else dados.get("banco_id")
    return (
        dados["tipo"], dados["data"], (dados.get("descricao") or "").strip() or None, dados["categoria_id"],
        dados["valor"], dados["forma"], banco_id, (dados.get("observacao") or "").strip() or None,
    )


_CAMPOS = "tipo, data, descricao, categoria_id, valor, forma, banco_id, observacao"


_INSERIR = f"INSERT INTO fin_lancamentos ({_CAMPOS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"


def criar_lancamento(dados):
    with get_cursor() as cur:
        _conferir_categoria(cur, dados)
        cur.execute(_INSERIR, _valores(dados))
        return cur.lastrowid


def criar_lancamentos(lista):
    with get_cursor() as cur:
        for dados in lista:
            _conferir_categoria(cur, dados)
            cur.execute(_INSERIR, _valores(dados))
    return len(lista)


def atualizar_lancamento(lancamento_id, dados):
    """False se o lançamento já não existe (excluído em outra aba, por exemplo)."""
    with get_cursor() as cur:
        _conferir_categoria(cur, dados)
        cur.execute("SELECT 1 FROM fin_lancamentos WHERE id = %s", (lancamento_id,))
        if cur.fetchone() is None:
            return False
        cur.execute(
            "UPDATE fin_lancamentos SET tipo=%s, data=%s, descricao=%s, categoria_id=%s, valor=%s, forma=%s, "
            "banco_id=%s, observacao=%s WHERE id=%s",
            _valores(dados) + (lancamento_id,),
        )
        return True


def excluir_lancamento(lancamento_id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM fin_lancamentos WHERE id=%s", (lancamento_id,))


def totais_por_mes(ate):
    """{primeiro dia do mês: (entradas, saídas)} de todos os meses até `ate`, e não só da janela mostrada: o
    fluxo de caixa acumula desde o começo."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT l.data - INTERVAL (DAYOFMONTH(l.data) - 1) DAY AS mes, "
            "SUM(CASE WHEN l.tipo = 'entrada' THEN l.valor ELSE 0 END) AS entradas, "
            "SUM(CASE WHEN l.tipo <> 'entrada' THEN l.valor ELSE 0 END) AS saidas "
            "FROM fin_lancamentos l WHERE l.data <= %s GROUP BY mes ORDER BY mes",
            (ate,),
        )
        linhas = cur.fetchall()
    return {registro["mes"]: (Decimal(registro["entradas"]), Decimal(registro["saidas"])) for registro in linhas}


NOME_MAX = 80


def obter_meu_nome():
    with get_cursor() as cur:
        cur.execute("SELECT valor FROM fin_config WHERE chave = 'meu_nome'")
        linha = cur.fetchone()
    return linha["valor"] if linha else ""


def definir_meu_nome(nome):
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO fin_config (chave, valor) VALUES ('meu_nome', %s) "
            "ON DUPLICATE KEY UPDATE valor = VALUES(valor)",
            ((nome or "").strip()[:NOME_MAX],),
        )


def listar_regras():
    with get_cursor() as cur:
        cur.execute(
            "SELECT r.id, r.padrao, r.categoria_id, c.nome AS categoria_nome, r.tipo, r.ignorar "
            "FROM fin_regras r LEFT JOIN fin_categorias c ON c.id = r.categoria_id ORDER BY r.padrao"
        )
        return cur.fetchall()


def lembrar_regra(padrao, categoria_id, tipo):
    """Regra gravada pela revisão da importação: só o que veio (None não apaga o que já existia) e sem tocar em
    "ignorar"."""
    padrao = normalizar(padrao)[:80]
    if not padrao:
        return
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO fin_regras (padrao, categoria_id, tipo, ignorar) VALUES (%s, %s, %s, 0) "
            "ON DUPLICATE KEY UPDATE categoria_id = COALESCE(VALUES(categoria_id), categoria_id), "
            "tipo = COALESCE(VALUES(tipo), tipo)",
            (padrao, categoria_id, tipo),
        )


def criar_regra(padrao, categoria_id, tipo, ignorar):
    """Regra criada à mão: um padrão repetido é recusado."""
    with duplicidade(NomeDuplicado, padrao), get_cursor() as cur:
        cur.execute(
            "INSERT INTO fin_regras (padrao, categoria_id, tipo, ignorar) VALUES (%s, %s, %s, %s)",
            (normalizar(padrao)[:80], categoria_id, tipo, int(bool(ignorar))),
        )
        return cur.lastrowid


def atualizar_regra(regra_id, padrao, categoria_id, tipo, ignorar):
    with duplicidade(NomeDuplicado, padrao), get_cursor() as cur:
        cur.execute(
            "UPDATE fin_regras SET padrao=%s, categoria_id=%s, tipo=%s, ignorar=%s WHERE id=%s",
            (normalizar(padrao)[:80], categoria_id, tipo, int(bool(ignorar)), regra_id),
        )


def excluir_regra(regra_id):
    with get_cursor() as cur:
        cur.execute("DELETE FROM fin_regras WHERE id=%s", (regra_id,))


def lancamentos_para_sugestao(limite=5000):
    with get_cursor() as cur:
        cur.execute(
            "SELECT descricao, categoria_id, tipo, data, valor FROM fin_lancamentos "
            "WHERE descricao IS NOT NULL AND descricao <> '' ORDER BY data DESC, id DESC LIMIT %s",
            (limite,),
        )
        return cur.fetchall()


def chaves_existentes(banco_id, chaves):
    chaves = list(dict.fromkeys(chaves))
    existentes = Counter()
    with get_cursor() as cur:
        for i in range(0, len(chaves), 500):
            lote = chaves[i:i + 500]
            marcas = ", ".join(["%s"] * len(lote))
            cur.execute(
                f"SELECT chave_externa, COUNT(*) AS n FROM fin_lancamentos "
                f"WHERE banco_id <=> %s AND chave_externa IN ({marcas}) GROUP BY chave_externa",
                (banco_id, *lote),
            )
            existentes.update({registro["chave_externa"]: registro["n"] for registro in cur.fetchall()})
    return existentes


def registrar_importacao(meta, lancamentos):
    """Grava a importação e todos os lançamentos dela numa transação e devolve o id da importação.

    `meta` leva arquivo, banco_id, origem, observacao, periodo_inicio, periodo_fim, qtd_lidas,
    qtd_duplicadas e qtd_ignoradas. Cada lançamento tem os campos de `criar_lancamento` mais `chave_externa`."""
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO fin_importacoes (arquivo, banco_id, origem, observacao, periodo_inicio, periodo_fim, "
            "qtd_lidas, qtd_importadas, qtd_duplicadas, qtd_ignoradas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (meta["arquivo"][:255], meta["banco_id"], meta["origem"], (meta.get("observacao") or "").strip()[:255] or None,
             meta["periodo_inicio"], meta["periodo_fim"], meta["qtd_lidas"], len(lancamentos),
             meta["qtd_duplicadas"], meta["qtd_ignoradas"]),
        )
        importacao_id = cur.lastrowid
        for dados in lancamentos:
            _conferir_categoria(cur, dados)
            cur.execute(
                f"INSERT INTO fin_lancamentos ({_CAMPOS}, importacao_id, chave_externa) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                _valores(dados) + (importacao_id, dados.get("chave_externa")),
            )
    return importacao_id


def listar_importacoes(limite=50):
    with get_cursor() as cur:
        cur.execute(
            "SELECT i.id, i.data_hora, i.arquivo, i.banco_id, i.origem, i.observacao, i.periodo_inicio, "
            "i.periodo_fim, i.qtd_lidas, i.qtd_importadas, i.qtd_duplicadas, i.qtd_ignoradas, i.status, "
            "b.nome AS banco_nome, b.sigla AS banco_sigla, b.cor AS banco_cor "
            "FROM fin_importacoes i LEFT JOIN fin_bancos b ON b.id = i.banco_id "
            "ORDER BY i.data_hora DESC, i.id DESC LIMIT %s",
            (limite,),
        )
        return cur.fetchall()


def contar_lancamentos_importacao(importacao_id):
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM fin_lancamentos WHERE importacao_id = %s", (importacao_id,))
        return cur.fetchone()["n"]


def desfazer_importacao(importacao_id):
    """Apaga os lançamentos da importação (inclusive os editados depois) e a marca como desfeita. Devolve
    quantos foram apagados, ou None se ela não existe ou já foi desfeita."""
    with get_cursor() as cur:
        cur.execute("SELECT status FROM fin_importacoes WHERE id = %s FOR UPDATE", (importacao_id,))
        linha = cur.fetchone()
        if linha is None or linha["status"] == "desfeita":
            return None
        cur.execute("DELETE FROM fin_lancamentos WHERE importacao_id = %s", (importacao_id,))
        apagados = cur.rowcount
        cur.execute("UPDATE fin_importacoes SET status = 'desfeita' WHERE id = %s", (importacao_id,))
        return apagados
