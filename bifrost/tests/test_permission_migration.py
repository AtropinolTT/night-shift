"""Integration tests for config_migrate — read-only Claude Code → OpenCode
permission settings migration tool.

Verifies:
  - Real config output correctness, no secrets leaked, no source modification
  - Graceful handling of empty, missing, secrets-only, and full-featured files
  - All 8 transform rules: permissions (1:1), model, allow_write_to_workspace,
    browser, allowedBashCommands, verbose, env filtering, unknown keys
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from companion.permission.migrate import config_migrate


class TestPermissionMigration:
    """Integration tests for the config_migrate MCP tool."""

    # ── Test 1: Real ~/.claude/settings.json ──────────────────────────

    def test_real_config_output_valid_no_secrets_file_unmodified(self):
        """Run on real settings.json — sections present, no secrets,
        source file not modified."""
        settings_path = Path.home() / ".claude" / "settings.json"
        if not settings_path.exists():
            pytest.skip(f"{settings_path} does not exist")

        # Capture md5 before
        original_hash = hashlib.md5(settings_path.read_bytes()).hexdigest()

        result = config_migrate(str(settings_path))

        # md5 after — file unmodified (read-only tool guarantee)
        after_hash = hashlib.md5(settings_path.read_bytes()).hexdigest()
        assert original_hash == after_hash, (
            "config_migrate MUST NOT modify source file"
        )

        # Output shape
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Migration from Claude Code settings" in result
        assert "Source:" in result

        # Sections present (real config has model, env, unknown keys)
        assert "---" in result

        # Secrets filtered — no raw token values leaked
        assert "sk-5c9a" not in result
        assert "FILTERED" in result

        # Unknown keys flagged (enabledPlugins, effortLevel, etc. in real config)
        assert "MANUAL REVIEW REQUIRED" in result

    # ── Test 2: Empty file ────────────────────────────────────────────

    def test_empty_file_returns_header_no_crash(self):
        """Empty JSON ({}) — graceful output, no exception."""
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("{}")
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert isinstance(result, str)
            assert "Migration from Claude Code settings" in result
            # No transforms applied, no unknown keys — no review flags
            assert "MANUAL REVIEW REQUIRED" not in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_whitespace_only_file_no_crash(self):
        """Whitespace-only JSON still parses to {}. Should not crash."""
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("  {  }  ")
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert isinstance(result, str)
            assert "Migration from Claude Code settings" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    # ── Test 3: Missing file ──────────────────────────────────────────

    def test_missing_file_returns_not_found_message(self):
        """Nonexistent path → 'No Claude Code config found at' message."""
        result = config_migrate("/tmp/bifrost_test_nonexistent_cc_settings.json")
        assert "No Claude Code config found at" in result

    # ── Test 4: Secrets only ──────────────────────────────────────────

    def test_secrets_only_all_filtered(self):
        """File with only secret-bearing keys — all filtered, no raw values."""
        secrets_config = {
            "ANTHROPIC_AUTH_TOKEN": "sk-12345678901234567890",
            "OPENAI_API_KEY": "sk-abcdefghijklmnopqrstuv",
            "some_api_key": "abcdef1234567890abcdef1234567890abcdef1234567890",
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "sk-aaaaaaaaaaaaaaaaaaaa",
                "secret_token": (
                    "dGhpc2lzYXRlc3R0b2tlbnRoaXNpc2F0ZXN0"
                    "b2tlbnRoaXNpc2E="
                ),
            },
        }

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(secrets_config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert isinstance(result, str)

            # No raw secret values leaked
            assert "sk-12345678901234567890" not in result
            assert "sk-abcdefghijklmnopqrstuv" not in result
            assert "sk-aaaaaaaaaaaaaaaaaaaa" not in result

            # FILTERED markers present (env section + unknown keys section)
            assert result.count("FILTERED") >= 3

            # Env secrets detection warning
            assert "secrets detected and filtered from env" in result

            # Unknown key names still present but values filtered in review block
            assert "ANTHROPIC_AUTH_TOKEN" in result
            assert "OPENAI_API_KEY" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    # ── Test 5: Synthetic fixture with all permission types ───────────

    def test_synthetic_fixture_all_permission_types_mapped(self):
        """Synthetic config exercising every known transform rule."""
        synthetic = {
            "permissions": {
                "allow": ["Read", "Edit", "Bash"],
                "deny": ["Bash(python3:*)", "WebFetch(github.com:*)"],
                "ask": ["Write"],
            },
            "allow_write_to_workspace": True,
            "model": "sonnet",
            "browser": True,
            "allowedBashCommands": ["ls", "git diff", "pytest"],
            "verbose": True,
            "env": {
                "DEBUG": "1",
                "OPENAI_API_KEY": "sk-should-be-filtered-xxxxxxxxxx",
                "EDITOR": "vim",
                "PYTHONPATH": "./src",
            },
            # Unknown key → MANUAL REVIEW
            "customScripts": {"lint": "ruff check ."},
        }

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(synthetic, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)

            # --- 1:1 permissions ---
            assert "permissions.allow" in result
            assert '"Read"' in result
            assert '"Edit"' in result
            assert "permissions.deny" in result
            assert "permissions.ask" in result
            assert '"Write"' in result

            # --- allow_write_to_workspace → Write ---
            assert "allow_write_to_workspace" in result
            assert 'permissions.allow += ["Write"]' in result
            assert "workspace write enabled" in result

            # --- model → deepseek mapping ---
            assert "deepseek-v4-flash" in result
            assert "sonnet" in result  # original model name shown in comment

            # --- browser → playwright MCP ---
            assert "playwright" in result

            # --- allowedBashCommands → bash: prefix ---
            assert "bash:ls" in result
            assert "bash:git diff" in result
            assert "bash:pytest" in result

            # --- env — secrets filtered, non-secrets preserved ---
            assert "FILTERED" in result
            assert "sk-should-be-filtered" not in result
            assert '"vim"' in result or "vim" in result

            # --- verbose → MANUAL REVIEW (no equivalent) ---
            assert "verbose" in result

            # --- unknown keys → MANUAL REVIEW REQUIRED section ---
            assert "customScripts" in result

            # Overall structure
            assert "Migration from Claude Code settings" in result
            assert "MANUAL REVIEW REQUIRED" in result

        finally:
            Path(temp_path).unlink(missing_ok=True)

    # ── Edge cases ────────────────────────────────────────────────────

    def test_flat_permissions_format_supported(self):
        """Flat-style ``permissions.allow`` keys should resolve correctly."""
        flat_config = {
            "permissions.allow": ["Read", "Grep"],
            "permissions.deny": ["Bash(curl:*)", "Write"],
        }

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(flat_config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "permissions.allow" in result
            assert '"Read"' in result
            assert "permissions.deny" in result
            assert "Bash(curl:*)" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_malformed_json_returns_parse_error(self):
        """Invalid JSON → parse error message, no crash."""
        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            fh.write("{ invalid json content {{{")
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "Error parsing" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_allow_write_to_workspace_false_no_op(self):
        """``allow_write_to_workspace: false`` → comment only, no Write add."""
        config = {"allow_write_to_workspace": False}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "allow_write_to_workspace" in result
            assert "no change needed" in result
            assert 'permissions.allow += ["Write"]' not in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_browser_false_no_playwright(self):
        """``browser: false`` → comment only, no playwright enabled."""
        config = {"browser": False}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "browser" in result.lower()
            assert "playwright MCP not enabled" in result
            assert "enabled: true" not in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_browser_true_manual_review_warning(self):
        """``browser: true`` → includes manual-review warning for MCP config."""
        config = {"browser": True}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "MANUAL REVIEW REQUIRED" in result
            assert "playwright" in result
            assert "enabled: true" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_model_mapping_sonnet_to_flash(self):
        """``model: sonnet`` → deepseek-v4-flash with source annotation."""
        config = {"model": "sonnet"}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert 'deepseek-v4-flash' in result
            assert 'sonnet' in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_model_mapping_opus_to_pro(self):
        """``model: opus`` → deepseek-v4-pro."""
        config = {"model": "opus"}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert 'deepseek-v4-pro' in result
            assert 'opus' in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_unknown_model_passthrough(self):
        """Unknown model name → passed through as-is."""
        config = {"model": "gpt-4"}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert 'gpt-4' in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_models_dict_form(self):
        """``models`` as a dict with multiple entries."""
        config = {"models": {"default": "sonnet", "quick": "haiku"}}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "deepseek-v4-flash" in result
            assert "default" in result
            assert "quick" in result
            assert "haiku" in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_empty_bash_commands_no_section(self):
        """Empty ``allowedBashCommands`` → no bash section emitted."""
        config = {"allowedBashCommands": []}

        with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            temp_path = fh.name

        try:
            result = config_migrate(temp_path)
            assert "allowedBashCommands" not in result
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_source_path_tilde_expansion(self):
        """Tilde in path → expanded to home directory."""
        # Use a nonexistent file in home to test expansion without needing
        # a real file
        result = config_migrate("~/nonexistent_bifrost_test_file_xyz.json")
        assert "No Claude Code config found at" in result
        # The path in the error message should be resolved (no ~)
        assert "~" not in result.split("No Claude Code config found at ")[1]
