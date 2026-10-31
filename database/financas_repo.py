"""Consultas do Controle Financeiro (tabelas `fin_*`, sem ligação com as Metas Pessoais)."""
from decimal import Decimal

from mysql.connector.errors import IntegrityError

from database.connection import get_cursor
from database.financas_calculos import ZERO, grupo_categoria
from database.financas_padroes import COR_OUTROS, NOME_OUTROS


class NomeDuplicado(Exception):
    """Já existe categoria (do mesmo tipo) ou banco com esse nome."""


class CategoriaProtegida(Exception):
    """A categoria "Outros" recebe os lançamentos das excluídas e não pode ser apagada."""


class CategoriaIncompativel(ValueError):
    """Entrada com categoria de gasto (ou o contrário), ou categoria que não existe mais."""


# ---------- categorias ----------

def listar_categorias(tipo=None):
    """Categorias com `em_uso` (quantos lançamentos usam cada uma); `tipo` 'entrada' ou 'gasto' filtra.

    "Outros" fica sempre por último dentro de cada tipo.
    """
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
    try:
        with get_cursor() as cur:
            cur.execute("INSERT INTO fin_categorias (tipo, nome, cor) VALUES (%s, %s, %s)", (tipo, nome, cor))
            return cur.lastrowid
    except IntegrityError as e:
        raise NomeDuplicado(nome) from e


def atualizar_categoria(categoria_id, nome, cor):
    try:
        with get_cursor() as cur:
            cur.execute("UPDATE fin_categorias SET nome=%s, cor=%s WHERE id=%s", (nome, cor, categoria_id))
    except IntegrityError as e:
        raise NomeDuplicado(nome) from e


def excluir_categoria(categoria_id):
    """Passa os lançamentos para a "Outros" do mesmo tipo e apaga a categoria. Devolve quantos mudaram."""
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
        if outros is None:  # banco montado à mão sem a "Outros" protegida: cria (ou protege a que houver)
            cur.execute(
                "INSERT INTO fin_categorias (tipo, nome, cor, protegida) VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE protegida = 1, id = LAST_INSERT_ID(id)",
                (categoria["tipo"], NOME_OUTROS, COR_OUTROS),
            )
            outros = {"id": cur.lastrowid}
        cur.execute("UPDATE fin_lancamentos SET categoria_id=%s WHERE categoria_id=%s", (outros["id"], categoria_id))
        movidos = cur.rowcount
        cur.execute("DELETE FROM fin_categorias WHERE id=%s", (categoria_id,))
        return movidos


# ---------- bancos ----------

def listar_bancos(incluir_ocultos=False):
    """Bancos com `em_uso`; por padrão só os ativos (os que aparecem no formulário)."""
    filtro = "" if incluir_ocultos else "WHERE b.ativo = 1"
    with get_cursor() as cur:
        cur.execute(
            "SELECT b.id, b.nome, b.sigla, b.cor, b.ativo, COUNT(l.id) AS em_uso FROM fin_bancos b "
            f"LEFT JOIN fin_lancamentos l ON l.banco_id = b.id {filtro} GROUP BY b.id ORDER BY b.nome"
        )
        return cur.fetchall()


def criar_banco(nome, sigla, cor):
    try:
        with get_cursor() as cur:
            cur.execute("INSERT INTO fin_bancos (nome, sigla, cor) VALUES (%s, %s, %s)", (nome, sigla, cor))
            return cur.lastrowid
    except IntegrityError as e:
        raise NomeDuplicado(nome) from e


def atualizar_banco(banco_id, nome, sigla, cor):
    try:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE fin_bancos SET nome=%s, sigla=%s, cor=%s WHERE id=%s", (nome, sigla, cor, banco_id),
            )
    except IntegrityError as e:
        raise NomeDuplicado(nome) from e


def definir_banco_ativo(banco_id, ativo):
    """Ocultar tira o banco do formulário; os lançamentos antigos continuam mostrando o nome dele."""
    with get_cursor() as cur:
        cur.execute("UPDATE fin_bancos SET ativo=%s WHERE id=%s", (int(bool(ativo)), banco_id))


def excluir_banco(banco_id):
    """Apaga o banco; os lançamentos dele ficam sem banco (FK `ON DELETE SET NULL`). Devolve quantos."""
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM fin_lancamentos WHERE banco_id=%s", (banco_id,))
        afetados = cur.fetchone()["n"]
        cur.execute("DELETE FROM fin_bancos WHERE id=%s", (banco_id,))
        return afetados


# ---------- configuração ----------

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


# ---------- lançamentos ----------

_SELECT_LANCAMENTOS = (
    "SELECT l.id, l.tipo, l.data, l.descricao, l.categoria_id, l.valor, l.forma, l.banco_id, l.observacao, "
    "c.nome AS categoria_nome, c.cor AS categoria_cor, "
    "b.nome AS banco_nome, b.sigla AS banco_sigla, b.cor AS banco_cor "
    "FROM fin_lancamentos l JOIN fin_categorias c ON c.id = l.categoria_id "
    "LEFT JOIN fin_bancos b ON b.id = l.banco_id "
)


def listar_lancamentos(inicio, fim, tipo=None):
    """Lançamentos com data entre `inicio` e `fim` (inclusive), mais recentes primeiro."""
    filtro, params = ("AND l.tipo = %s", (inicio, fim, tipo)) if tipo else ("", (inicio, fim))
    with get_cursor() as cur:
        cur.execute(
            _SELECT_LANCAMENTOS + f"WHERE l.data BETWEEN %s AND %s {filtro} ORDER BY l.data DESC, l.id DESC",
            params,
        )
        return cur.fetchall()


def _conferir_categoria(cur, dados):
    """A tela já filtra as categorias pelo tipo; aqui é a última barreira antes de gravar."""
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


def criar_lancamento(dados):
    """`dados`: tipo, data, descricao, categoria_id, valor (Decimal > 0), forma, banco_id, observacao."""
    with get_cursor() as cur:
        _conferir_categoria(cur, dados)
        cur.execute(f"INSERT INTO fin_lancamentos ({_CAMPOS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    _valores(dados))
        return cur.lastrowid


def criar_lancamentos(lista):
    """Grava vários de uma vez (cópia dos fixos): tudo ou nada."""
    with get_cursor() as cur:
        for dados in lista:
            _conferir_categoria(cur, dados)
            cur.execute(f"INSERT INTO fin_lancamentos ({_CAMPOS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        _valores(dados))
    return len(lista)


def atualizar_lancamento(lancamento_id, dados):
    """Devolve False se o lançamento não existe mais (excluído em outra aba, por exemplo)."""
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
    """{primeiro dia do mês: (entradas, saídas)} de todos os meses com lançamento até a data `ate`.

    Inclui os meses antigos porque o fluxo de caixa acumula desde o começo.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT l.data - INTERVAL (DAYOFMONTH(l.data) - 1) DAY AS mes, "
            "SUM(CASE WHEN l.tipo = 'entrada' THEN l.valor ELSE 0 END) AS entradas, "
            "SUM(CASE WHEN l.tipo <> 'entrada' THEN l.valor ELSE 0 END) AS saidas "
            "FROM fin_lancamentos l WHERE l.data <= %s GROUP BY mes ORDER BY mes",
            (ate,),
        )
        linhas = cur.fetchall()
    return {l["mes"]: (Decimal(l["entradas"]), Decimal(l["saidas"])) for l in linhas}
