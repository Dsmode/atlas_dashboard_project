import os
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from mysql.connector.errors import IntegrityError

from database.financas import padroes

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

load_dotenv(BASE_DIR / ".env")

DB_NAME = "atlas_db"


def _config(com_banco=True):
    cfg = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
    }
    if com_banco:
        cfg["database"] = DB_NAME
    return cfg


def _coluna_existe(cur, tabela, coluna):
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        (DB_NAME, tabela, coluna),
    )
    return cur.fetchone()[0] > 0


def _indice_existe(cur, tabela, indice):
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s",
        (DB_NAME, tabela, indice),
    )
    return cur.fetchone()[0] > 0


def _adicionar_colunas(cur, tabela, colunas):
    adicionadas = []
    for coluna, definicao in colunas:
        if not _coluna_existe(cur, tabela, coluna):
            cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
            adicionadas.append(coluna)
    return adicionadas


def _migrar(cur):
    """Ajusta bancos criados por versões antigas do schema: colunas e índice que foram chegando depois."""
    if not _coluna_existe(cur, "tarefas_meta", "ordem"):
        cur.execute("ALTER TABLE tarefas_meta ADD COLUMN ordem INT NOT NULL DEFAULT 0 AFTER prazo")
        cur.execute("UPDATE tarefas_meta SET ordem = id")
    _adicionar_colunas(cur, "metas", (
        ("tipo_progresso", "ENUM('tarefas', 'quantidade', 'valor') NOT NULL DEFAULT 'tarefas'"),
        ("objetivo", "ENUM('aumentar', 'reduzir') NOT NULL DEFAULT 'aumentar'"),
        ("unidade", "VARCHAR(30) NULL"),
        ("valor_inicial", "DECIMAL(14, 2) NULL"),
        ("valor_alvo", "DECIMAL(14, 2) NULL"),
        ("valor_atual", "DECIMAL(14, 2) NULL"),
    ))
    adicionadas = _adicionar_colunas(cur, "fin_lancamentos", (
        ("importacao_id", "INT NULL"),
        ("chave_externa", "VARCHAR(64) NULL"),
    ))
    if "importacao_id" in adicionadas:
        cur.execute(
            "ALTER TABLE fin_lancamentos ADD CONSTRAINT fk_fin_lancamentos_importacao "
            "FOREIGN KEY (importacao_id) REFERENCES fin_importacoes (id) ON DELETE SET NULL"
        )
    if not _indice_existe(cur, "fin_lancamentos", "idx_fin_lancamentos_chave"):
        cur.execute("ALTER TABLE fin_lancamentos ADD INDEX idx_fin_lancamentos_chave (banco_id, chave_externa)")


def _comandos(sql):
    """Divide o schema em comandos, ignorando ';' dentro de strings e comentários."""
    comandos, atual, i = [], [], 0
    while i < len(sql):
        c = sql[i]
        if sql.startswith("--", i):
            fim_linha = sql.find("\n", i)
            i = len(sql) if fim_linha < 0 else fim_linha
            continue
        if c in "'\"`":
            fim = i + 1
            while fim < len(sql) and sql[fim] != c:
                fim += 2 if sql[fim] == "\\" else 1
            atual.append(sql[i:fim + 1])
            i = fim + 1
            continue
        if c == ";":
            comandos.append("".join(atual).strip())
            atual = []
        else:
            atual.append(c)
        i += 1
    comandos.append("".join(atual).strip())
    return [c for c in comandos if c]


def init_db():
    """Cria o banco e as tabelas a partir do schema.sql; pode rodar quantas vezes precisar."""
    conn = mysql.connector.connect(**_config(com_banco=False))
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE {DB_NAME}")
        for comando in _comandos(SCHEMA_PATH.read_text(encoding="utf-8")):
            cur.execute(comando)
        _migrar(cur)
        padroes.criar_padroes(cur)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def duplicidade(erro, nome):
    """Converte qualquer IntegrityError em `erro(nome)`. Hoje o único caso esperado é nome repetido."""
    try:
        yield
    except IntegrityError as e:
        raise erro(nome) from e


@contextmanager
def get_cursor():
    """Cursor de dicionário com commit ao sair do bloco e rollback se algo falhar. Cada uso abre uma conexão própria."""
    conn = mysql.connector.connect(**_config())
    try:
        cur = conn.cursor(dictionary=True)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
