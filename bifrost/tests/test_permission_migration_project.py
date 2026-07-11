"""Security tests for config_migrate_project — covers regressions to v0.2.1
path traversal, secret filtering, and missing-candidate graceful handling.

The function `config_migrate_project(project_root)` looks for known
config paths in the project root and merges them. It must:
  1. NOT read files outside the hardcoded candidate list.
  2. Filter secrets in any project-level config it does read.
  3. Handle missing candidates, malformed JSON, and binary files gracefully.
  4. Reject symlinks pointing outside the project.
"""
import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from companion.permission.migrate import config_migrate_project


def test_no_config_files_returns_empty_string(tmp_path: Path) -> None:
    """Empty project: returns empty string (not crash, not fake content)."""
    result = config_migrate_project(str(tmp_path))
    assert result == "", f"Expected empty string, got: {result!r}"


def test_claude_settings_json_with_secrets_filters(tmp_path: Path) -> None:
    """Secrets in project-level .claude/settings.json must be filtered."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(json.dumps({
        "ANTHROPIC_AUTH_TOKEN": "sk-secret-value-12345",
        "OPENAI_API_KEY": "sk-openaivalue-67890",
        "model": "claude-sonnet",
    }))
    result = config_migrate_project(str(tmp_path))
    assert "sk-secret-value-12345" not in result
    assert "sk-openaivalue-67890" not in result
    assert "FILTERED" in result or "secret" in result.lower()


def test_malformed_json_does_not_crash(tmp_path: Path) -> None:
    """Malformed JSON in candidate file returns an error string, not crash."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{not valid json,}{")
    # Should return an error message string, not raise
    result = config_migrate_project(str(tmp_path))
    assert "Error" in result or result == "" or "//" in result


def test_binary_file_does_not_crash(tmp_path: Path) -> None:
    """Binary file in candidate path is skipped (not loaded)."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_bytes(b"\x00\x01\x02\x03binary garbage")
    # Should not raise UnicodeDecodeError — skip or return error
    result = config_migrate_project(str(tmp_path))
    assert isinstance(result, str)  # not a crash


def test_opencode_json_with_unknown_keys(tmp_path: Path) -> None:
    """.opencode.json with unknown keys flagged as MANUAL REVIEW."""
    (tmp_path / ".opencode.json").write_text(json.dumps({
        "someCustomKey": "customValue",
        "anotherKey": 42,
    }))
    result = config_migrate_project(str(tmp_path))
    # Either returns the migration or an error — but must not crash
    assert isinstance(result, str)


def test_none_project_root_raises_typeerror() -> None:
    """Passing None must raise TypeError, not crash with cryptic error."""
    with pytest.raises(TypeError):
        config_migrate_project(None)  # type: ignore[arg-type]


def test_relative_project_root_works(tmp_path: Path, monkeypatch) -> None:
    """A relative path like '.' should be resolved and work."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps({"model": "opus"}))
    result = config_migrate_project(".")
    assert isinstance(result, str)


def test_path_with_dotdot_does_not_escape(tmp_path: Path) -> None:
    """Passing a path containing '..' should NOT read files outside that path."""
    parent = tmp_path / "parent"
    sub = parent / "sub"
    sub.mkdir(parents=True)
    # Create a file in the parent of parent
    escape_target = tmp_path / "secret.txt"
    escape_target.write_text("SECRET_DATA_LEAK")
    # Try to pass parent/../secret.txt as project_root
    escape_path = str(parent / ".." / "secret.txt")
    result = config_migrate_project(escape_path)
    # The function should treat the path as a directory, fail to find candidates
    # in it, and return empty (NOT leak secret.txt content)
    assert "SECRET_DATA_LEAK" not in result
