from typing import Any

from companion.db import get_db


def list_memories(
    scope: str | None = None,
    type_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    type_list = [t.strip() for t in type_filter.split(",") if t.strip()] if type_filter else None

    with get_db() as db:
        sql = """SELECT id, type, content, scope, created_at, deleted_at
                 FROM memories
                 WHERE deleted_at IS NULL"""
        params: list[Any] = []

        if scope:
            sql += " AND scope = ?"
            params.append(scope)
        if type_list:
            placeholders = ",".join("?" for _ in type_list)
            sql += f" AND type IN ({placeholders})"
            params.extend(type_list)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = db.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
