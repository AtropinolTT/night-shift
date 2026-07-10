import time

import pytest

from companion.db import get_db
from companion.memory.context import search_memory
from companion.memory.list import list_memories
from companion.memory.store import delete_memory, save_memory


def _fts_count() -> int:
    with get_db() as db:
        return db.execute("SELECT count(*) FROM memories_fts").fetchone()[0]


def _memory_count() -> int:
    with get_db() as db:
        return db.execute("SELECT count(*) FROM memories").fetchone()[0]


class TestMemoryIntegration:
    """End-to-end memory subsystem tests using a real temp SQLite database."""

    def test_save_all_types_and_scopes(self):
        id1 = save_memory("decision", "Use Ruff for linting", "user")
        id2 = save_memory("pattern", "Always annotate return types", "user")
        id3 = save_memory("fact", "Python 3.13 is the default runtime", "project")
        id4 = save_memory("feedback", "Prefer composition over inheritance", "project")
        id5 = save_memory("decision", "Adopt uv for dependency management", "user")

        assert all(isinstance(i, int) for i in [id1, id2, id3, id4, id5])
        assert len({id1, id2, id3, id4, id5}) == 5
        assert _memory_count() == 5

    def test_fts_auto_index_on_insert(self):
        """Trigger-based FTS sync fires on INSERT (simulates session.compacting hook)."""
        save_memory("decision", "Use Ruff for project linting", "user")
        assert _fts_count() >= 1

        save_memory("decision", "Adopt uv for dependency management", "user")
        assert _fts_count() >= 2

    def test_keyword_search_returns_relevant_results(self):
        save_memory("decision", "Use Ruff for linting in CI pipeline", "user")
        save_memory("pattern", "Always type return types explicitly", "user")
        save_memory("fact", "Python 3.13 is the default runtime", "project")

        results = search_memory(query="Ruff")
        assert len(results) >= 1
        assert any("Ruff" in r["content"] for r in results)
        assert all(r["type"] == "decision" for r in results)

    def test_keyword_search_no_match_returns_empty(self):
        save_memory("fact", "Python 3.13 is the default runtime", "project")
        results = search_memory(query="xyznonexistentkeyword")
        assert len(results) == 0

    def test_empty_query_returns_most_recent(self):
        save_memory("decision", "Old decision", "user")
        time.sleep(1.1)
        save_memory("decision", "New decision", "user")
        results = search_memory(query=None, limit=1)
        assert len(results) == 1
        assert results[0]["content"] == "New decision"

    def test_empty_query_filters_by_scope(self):
        save_memory("fact", "User-scoped fact", "user")
        save_memory("fact", "Project-scoped fact", "project")
        user_results = search_memory(query=None, scope="user")
        proj_results = search_memory(query=None, scope="project")
        assert all(r["scope"] == "user" for r in user_results)
        assert all(r["scope"] == "project" for r in proj_results)

    def test_empty_query_filters_by_type(self):
        save_memory("decision", "A decision", "user")
        save_memory("fact", "A fact", "user")
        decisions = search_memory(query=None, type_filter=["decision"])
        facts = search_memory(query=None, type_filter=["fact"])
        assert len(decisions) >= 1
        assert len(facts) >= 1
        assert all(r["type"] == "decision" for r in decisions)
        assert all(r["type"] == "fact" for r in facts)

    def test_list_all_memories(self):
        save_memory("decision", "D1", "user")
        save_memory("fact", "F1", "project")
        save_memory("pattern", "P1", "user")
        mems = list_memories()
        assert len(mems) >= 3
        assert all(m["deleted_at"] is None for m in mems)
        ids = [m["id"] for m in mems]
        assert len(ids) == len(set(ids))

    def test_list_filter_by_scope(self):
        save_memory("decision", "User decision", "user")
        save_memory("fact", "Project fact", "project")
        user_mems = list_memories(scope="user")
        proj_mems = list_memories(scope="project")
        assert all(m["scope"] == "user" for m in user_mems)
        assert all(m["scope"] == "project" for m in proj_mems)
        assert len(user_mems) >= 1
        assert len(proj_mems) >= 1

    def test_list_filter_by_type_comma_separated(self):
        save_memory("decision", "A decision", "user")
        save_memory("fact", "A fact", "user")
        save_memory("pattern", "A pattern", "user")
        decisions_and_facts = list_memories(type_filter="decision,fact")
        assert all(m["type"] in ("decision", "fact") for m in decisions_and_facts)
        assert len(decisions_and_facts) >= 2

    def test_delete_sets_deleted_at_and_hides_from_list(self):
        mem_id = save_memory("decision", "Will be deleted", "user")
        result = delete_memory(mem_id)
        assert result is True

        with get_db() as db:
            row = db.execute(
                "SELECT deleted_at FROM memories WHERE id = ?", (mem_id,)
            ).fetchone()
            assert row is not None
            assert row["deleted_at"] is not None

        mems = list_memories()
        assert all(m["id"] != mem_id for m in mems)

    def test_delete_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found or already deleted"):
            delete_memory(99999)

    def test_delete_already_deleted_raises(self):
        mem_id = save_memory("decision", "Delete me twice", "user")
        delete_memory(mem_id)
        with pytest.raises(ValueError, match="not found or already deleted"):
            delete_memory(mem_id)

    def test_save_raises_on_invalid_type(self):
        with pytest.raises(ValueError, match="Invalid memory type"):
            save_memory("invalid_type", "bad", "user")

    def test_save_raises_on_empty_content(self):
        with pytest.raises(ValueError, match="content must not be empty"):
            save_memory("decision", "", "user")

    def test_deleted_memory_excluded_from_search(self):
        mem_id = save_memory("decision", "Searchable content for deletion test", "user")
        results_before = search_memory(query="Searchable content")
        assert len(results_before) >= 1
        assert mem_id in {r["id"] for r in results_before}

        delete_memory(mem_id)

        results_after = search_memory(query="Searchable content")
        assert mem_id not in {r["id"] for r in results_after}

    def test_scope_and_type_filter_together_on_search(self):
        save_memory("decision", "User decision alpha", "user")
        save_memory("fact", "User fact beta", "user")
        save_memory("decision", "Project decision gamma", "project")
        results = search_memory(query=None, scope="user", type_filter=["fact"])
        assert len(results) >= 1
        assert all(r["type"] == "fact" for r in results)
        assert all(r["scope"] == "user" for r in results)
