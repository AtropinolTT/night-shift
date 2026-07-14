"""Context injection integration tests for Bifrost.

Tests the full context pipeline: AGENTS.md loading, @import resolution,
path-scoped rule matching, and token-count truncation.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from companion.context.loader import load_context
from companion.context.rules import get_matching_rules


def _make_agents_md(directory: Path, content: str) -> Path:
    p = directory / "AGENTS.md"
    p.write_text(content, encoding="utf-8")
    return p


def _make_imported(directory: Path, name: str, content: str) -> Path:
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_rule(directory: Path, name: str, content: str) -> Path:
    rules_dir = directory / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    p = rules_dir / name
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def mock_config(monkeypatch):
    """Override load_config to return a known max_context_tokens."""

    def _fake_config(path=None):
        return SimpleNamespace(max_context_tokens=200)

    monkeypatch.setattr(
        "companion.context.loader.load_config", _fake_config
    )
    return _fake_config


class TestLoadContext:
    """Tests for ``load_context()`` — AGENTS.md discovery and @import
    resolution."""

    def test_no_agents_md_returns_empty(self, tmp_path):
        result = load_context(cwd=str(tmp_path))
        assert result["content"] == ""
        assert result["sources"] == []
        assert result["truncated"] is False

    def test_loads_agents_md_content(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "# Project rules\n- Use type hints")
        result = load_context(cwd=str(tmp_path))
        assert "- Use type hints" in result["content"]

    def test_empty_agents_md(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "")
        result = load_context(cwd=str(tmp_path))
        assert result["content"] == ""
        assert result["truncated"] is False

    def test_resolves_import_directive(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "before\n@shared.md\nafter")
        _make_imported(tmp_path, "shared.md", "imported content")
        result = load_context(cwd=str(tmp_path))
        assert "imported content" in result["content"]
        assert any("shared.md" in s for s in result["sources"])

    def test_nested_import(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "root\n@a.md")
        _make_imported(tmp_path, "a.md", "a\n@b.md")
        _make_imported(tmp_path, "b.md", "b content")
        result = load_context(cwd=str(tmp_path))
        assert "b content" in result["content"]

    def test_import_cycle_does_not_infinite_loop(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "@a.md")
        _make_imported(tmp_path, "a.md", "@AGENTS.md")
        result = load_context(cwd=str(tmp_path))
        assert "AGENTS.md" in result["content"] or "a.md" in result["content"]

    def test_import_outside_project_is_skipped(self, tmp_path, mock_config):
        sub = tmp_path / "subdir"
        sub.mkdir()
        _make_agents_md(sub, "before\n@../outside.md\nafter")
        outside = tmp_path / "outside.md"
        outside.write_text("outside content")
        result = load_context(cwd=str(sub))
        assert "skipped" in result["content"]

    def test_import_not_found_emits_comment(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "@nonexistent.md")
        result = load_context(cwd=str(tmp_path))
        assert "not found" in result["content"]

    def test_import_exceeds_max_depth(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "@a.md")
        _make_imported(tmp_path, "a.md", "@b.md")
        _make_imported(tmp_path, "b.md", "@c.md")
        _make_imported(tmp_path, "c.md", "c content")
        result = load_context(cwd=str(tmp_path))
        assert "c content" not in result["content"]

    def test_sources_includes_imported_files(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "@dep.md")
        dep_path = _make_imported(tmp_path, "dep.md", "dependency")
        result = load_context(cwd=str(tmp_path))
        assert str(dep_path.resolve()) in result["sources"]

    def test_user_file_loaded_when_project_file_exists(self, tmp_path, monkeypatch, mock_config):
        _make_agents_md(tmp_path, "project content")
        user_dir = tmp_path / ".config" / "opencode"
        user_dir.mkdir(parents=True)
        (user_dir / "AGENTS.md").write_text("user content", encoding="utf-8")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = load_context(cwd=str(tmp_path))
        assert "project content" in result["content"]
        assert "user content" in result["content"]

    def test_truncation_when_content_exceeds_max_tokens(self, tmp_path, mock_config):
        long_line = "A" * 5000
        _make_agents_md(tmp_path, long_line)
        result = load_context(cwd=str(tmp_path))
        assert result["truncated"] is True
        assert len(result["content"]) < len(long_line)

    def test_truncation_cuts_at_newline(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "line1\nline2\nline3\n" + "X" * 5000)
        result = load_context(cwd=str(tmp_path))
        assert result["truncated"] is True
        assert result["content"].endswith("line3")
        assert "XXXX" not in result["content"]

    def test_imported_content_also_truncated(self, tmp_path, mock_config):
        _make_agents_md(tmp_path, "@large.md")
        _make_imported(tmp_path, "large.md", "Y" * 5000)
        result = load_context(cwd=str(tmp_path))
        assert result["truncated"] is True
        assert len(result["content"]) < 5000


class TestGetMatchingRules:
    """Tests for ``get_matching_rules()`` — path-scoped rule matching."""

    def test_no_rules_dir_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: None,
        )
        assert get_matching_rules("any/file.py") == []

    def test_global_rule_without_paths_always_matches(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: tmp_path / ".claude" / "rules",
        )
        _make_rule(tmp_path, "global.md", "# Global\n- Always write tests")
        rules = get_matching_rules("some/file.ts")
        assert len(rules) == 1
        assert rules[0]["file"] == "global.md"

    def test_path_rule_matches_correct_extension(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: tmp_path / ".claude" / "rules",
        )
        _make_rule(
            tmp_path,
            "python.md",
            "---\npaths: ['**/*.py']\n---\n# Python rules",
        )
        assert len(get_matching_rules("src/main.py")) == 1
        assert get_matching_rules("src/main.ts") == []

    def test_brace_pattern_expansion(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: tmp_path / ".claude" / "rules",
        )
        _make_rule(
            tmp_path,
            "frontend.md",
            "---\npaths: ['src/**/*.{tsx,jsx}']\n---\n# Frontend",
        )
        assert len(get_matching_rules("src/comp/Button.tsx")) == 1
        assert len(get_matching_rules("src/comp/Button.jsx")) == 1
        assert get_matching_rules("src/comp/Button.ts") == []

    def test_malformed_frontmatter_skips_rule(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: tmp_path / ".claude" / "rules",
        )
        _make_rule(tmp_path, "bad.md", "---\npaths: [unclosed\n---\nBad")
        rules = get_matching_rules("any/file.py")
        assert all(r["file"] != "bad.md" for r in rules)

    def test_multiple_rules_returned_for_single_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: tmp_path / ".claude" / "rules",
        )
        _make_rule(tmp_path, "global.md", "# Global")
        _make_rule(
            tmp_path,
            "python.md",
            "---\npaths: ['**/*.py']\n---\n# Python",
        )
        _make_rule(
            tmp_path,
            "frontend.md",
            "---\npaths: ['**/*.tsx']\n---\n# Frontend",
        )
        rules = get_matching_rules("src/main.py")
        assert len(rules) == 2
        rule_files = {r["file"] for r in rules}
        assert rule_files == {"global.md", "python.md"}

    def test_empty_paths_list_treated_as_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "companion.context.rules._find_rules_dir",
            lambda: tmp_path / ".claude" / "rules",
        )
        _make_rule(
            tmp_path,
            "empty_paths.md",
            "---\npaths: []\n---\n# No specific paths",
        )
        rules = get_matching_rules("anything/foo.txt")
        assert len(rules) == 1
        assert rules[0]["file"] == "empty_paths.md"
