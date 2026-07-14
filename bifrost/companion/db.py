import logging
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
import threading

DB_DIR = Path.home() / ".bifrost"
DB_PATH = DB_DIR / "bifrost.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 2

_lock = threading.Lock()
_log = logging.getLogger(__name__)


def _ensure_dir():
    DB_DIR.mkdir(parents=True, exist_ok=True)


def _chmod(path: Path, mode: int) -> None:
    """Best-effort chmod. POSIX systems support full mode bits;
    Windows ignores most bits (still restricts ACL on creation)."""
    try:
        os.chmod(path, mode)
    except OSError:
        pass  # best-effort


def _verify_permissions(db_dir: Path, db_path: Path) -> bool:
    """Check DB directory and file permissions. Log warning if insecure.
    Returns True if permissions need fixing."""
    needs_fix = False
    for path, expected_mode in ((db_dir, 0o700), (db_path, 0o600)):
        try:
            if not path.exists():
                continue
            st = path.stat()
            actual = stat.S_IMODE(st.st_mode)
            if actual != expected_mode:
                _log.warning(
                    "[bifrost] %s has permissive mode %04o, expected %04o — "
                    "DB may contain secrets. Run: chmod %s %04o",
                    path, actual, expected_mode, path, expected_mode,
                )
                needs_fix = True
        except OSError:
            pass
    return needs_fix


def _apply_schema(conn: sqlite3.Connection):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    if cur.fetchone() is None:
        existing_version = 0
    else:
        row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
        existing_version = row[0] if row else 0

    if existing_version < SCHEMA_VERSION:
        # Apply full schema for new tables (CREATE TABLE IF NOT EXISTS handles existing)
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)

        # Apply additive migrations for existing tables
        if existing_version <= 1:
            # Migration v1 → v2: Add author column
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN author TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists

        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
            (SCHEMA_VERSION,),
        )
        conn.commit()


@contextmanager
def get_db():
    _ensure_dir()
    _verify_permissions(DB_DIR, DB_PATH)
    _chmod(DB_DIR, 0o700)   # owner-only directory
    with _lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            _apply_schema(conn)
            _chmod(DB_PATH, 0o600)   # owner-only file
            yield conn
        finally:
            conn.close()
