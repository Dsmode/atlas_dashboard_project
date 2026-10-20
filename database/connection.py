import os
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

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


def _migrar(cur):
    """Ajusta bancos criados por versões anteriores do schema."""
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='tarefas_meta' AND COLUMN_NAME='ordem'",
        (DB_NAME,),
    )
    if cur.fetchone()[0] == 0:
        cur.execute("ALTER TABLE tarefas_meta ADD COLUMN ordem INT NOT NULL DEFAULT 0 AFTER prazo")
        cur.execute("UPDATE tarefas_meta SET ordem = id")


def init_db():
    """Cria o banco e as tabelas (idempotente) executando o schema.sql."""
    linhas = [
        l for l in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if not l.strip().startswith("--")
    ]
    comandos = [c.strip() for c in "\n".join(linhas).split(";") if c.strip()]
    conn = mysql.connector.connect(**_config(com_banco=False))
    try:
        cur = conn.cursor()
        for comando in comandos:
            cur.execute(comando)
        _migrar(cur)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_cursor():
    """Entrega um cursor de dicionário e faz commit/rollback automaticamente."""
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
