PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('decision','pattern','fact','feedback','preference')),
    author TEXT,
    content TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('user','project')),
    project_hash TEXT,
    relevance_score REAL DEFAULT 0.0,
    version INTEGER DEFAULT 1,
    deleted_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    content='memories',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories WHEN old.content IS NOT new.content AND old.deleted_at IS NULL BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TABLE IF NOT EXISTS classifier_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    tool_args_short TEXT,
    decision TEXT NOT NULL CHECK(decision IN ('ALLOW','DENY','ASK_USER')),
    user_override TEXT,
    session_id TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS learned_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_pattern TEXT NOT NULL,
    learned_decision TEXT NOT NULL,
    override_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending_review' CHECK(status IN ('pending_review','active','rejected')),
    created_at TEXT DEFAULT (datetime('now')),
    reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- ── Composite indexes ────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_memories_scope_type
    ON memories(scope, type);

CREATE INDEX IF NOT EXISTS idx_memories_scope_deleted
    ON memories(scope, deleted_at);

CREATE INDEX IF NOT EXISTS idx_memories_type_deleted
    ON memories(type, deleted_at);

CREATE INDEX IF NOT EXISTS idx_classifier_feedback_created
    ON classifier_feedback(created_at);
