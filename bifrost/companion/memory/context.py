import sqlite3
from typing import Any

from companion.db import get_db


def _ensure_fts_index(db: sqlite3.Connection) -> None:
    fts_count = db.execute("SELECT count(*) FROM memories_fts").fetchone()[0]
    mem_count = db.execute("SELECT count(*) FROM memories WHERE deleted_at IS NULL").fetchone()[0]
    if fts_count < mem_count:
        db.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
        db.commit()


def search_memory(
    query: str | None = None,
    scope: str | None = None,
    type_filter: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    with get_db() as db:
        if not query:
            sql = """SELECT id, type, content, scope, created_at, 0 AS rank
                     FROM memories
                     WHERE deleted_at IS NULL"""
            params: list[Any] = []
            if scope:
                sql += " AND scope = ?"
                params.append(scope)
            if type_filter:
                placeholders = ",".join("?" for _ in type_filter)
                sql += f" AND type IN ({placeholders})"
                params.extend(type_filter)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = db.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

        _ensure_fts_index(db)

        sql = """SELECT m.id, m.type, m.content, m.scope, m.created_at, fts.rank
                 FROM memories_fts fts
                 JOIN memories m ON fts.rowid = m.id
                 WHERE memories_fts MATCH ?
                   AND m.deleted_at IS NULL"""
        params = [query]
        if scope:
            sql += " AND m.scope = ?"
            params.append(scope)
        if type_filter:
            placeholders = ",".join("?" for _ in type_filter)
            sql += f" AND m.type IN ({placeholders})"
            params.extend(type_filter)
        sql += " ORDER BY fts.rank LIMIT ?"
        params.append(limit)
        rows = db.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
