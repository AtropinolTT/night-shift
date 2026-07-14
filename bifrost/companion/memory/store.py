from companion.db import get_db

_VALID_TYPES = frozenset({"decision", "pattern", "fact", "feedback", "preference"})


def save_memory(type_: str, content: str, scope: str, project_hash: str | None = None) -> int:
    if type_ not in _VALID_TYPES:
        raise ValueError(
            f"Invalid memory type '{type_}'. Must be one of: {', '.join(sorted(_VALID_TYPES))}"
        )
    if not content:
        raise ValueError("content must not be empty")

    with get_db() as db:
        cur = db.execute(
            "INSERT INTO memories (type, content, scope, project_hash, version) VALUES (?, ?, ?, ?, 1)",
            (type_, content, scope, project_hash),
        )
        db.commit()
        return cur.lastrowid


def delete_memory(memory_id: int) -> bool:
    with get_db() as db:
        cur = db.execute(
            "UPDATE memories SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL",
            (memory_id,),
        )
        db.commit()
    if cur.rowcount == 0:
        raise ValueError(f"Memory with id {memory_id} not found or already deleted")
    return True
