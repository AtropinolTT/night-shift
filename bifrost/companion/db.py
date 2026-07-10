import sqlite3
from contextlib import contextmanager
from pathlib import Path
import threading

DB_DIR = Path.home() / ".bifrost"
DB_PATH = DB_DIR / "bifrost.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 2

_lock = threading.Lock()


def _ensure_dir():
    DB_DIR.mkdir(parents=True, exist_ok=True)


def _apply_schema(conn: sqlite3.Connection):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    if cur.fetchone() is None:
        existing_version = 0
    else:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
        existing_version = row[0] if row else 0

    if existing_version < SCHEMA_VERSION:
        schema_sql = SCHEMA_PATH.read_text()
        conn.executescript(schema_sql)
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()


@contextmanager
def get_db():
    _ensure_dir()
    with _lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            _apply_schema(conn)
            yield conn
        finally:
            conn.close()
