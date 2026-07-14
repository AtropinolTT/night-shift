"""Bifrost v0.1.0-alpha — Full Integration Smoke Test (T10.4)

Verifies all 7 features work with real modules (no mocks except where
modules themselves use mock dispatch like fusion_dispatch):

  1. Memory CRUD       — save, search, list, delete via real SQLite
  2. Tool Call Classifier — pre-filter for Known scenarios (Read/W/Bash)
  3. Goal-Oriented Agent Loop — monkeypatched classifier (zero model dispatch)
  4. Skill Bridge       — load caveman skill from real SKILL.md
  5. Permission Audit   — config_migrate on a minimal settings file
  6. Model Fusion       — fusion_dispatch with built-in mock
  7. Feedback & Learning — log_override × 5 → check_learned_rules

Plus: companion imports and an optional TypeScript compile check.

See conftest.py — every test uses an isolated temp SQLite DB.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

# ── Ensure companion is importable from the bifrost/ tree ───────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPANION_ROOT = _REPO_ROOT / "bifrost"
if str(_COMPANION_ROOT) not in sys.path:
    sys.path.insert(0, str(_COMPANION_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
#  0. Companion imports (sanity)
# ═══════════════════════════════════════════════════════════════════════════════


def test_companion_imports_without_errors():
    """Every core companion module imports cleanly in one shot."""
    from companion.server import mcp  # noqa: F401
    from companion.memory.store import save_memory, delete_memory  # noqa: F401
    from companion.memory.list import list_memories  # noqa: F401
    from companion.memory.context import search_memory  # noqa: F401
    from companion.classifier.classifier import classify_tool_call  # noqa: F401
    from companion.classifier.feedback import log_override, check_learned_rules  # noqa: F401
    from companion.goal.loop import goal_loop  # noqa: F401
    from companion.skill.loader import load_skill, _parse_frontmatter  # noqa: F401
    from companion.permission.migrate import config_migrate  # noqa: F401, E501
    from companion.fusion.dispatch import fusion_dispatch  # noqa: F401
    from companion.db import get_db, DB_PATH  # noqa: F401
    from companion.config import load_config  # noqa: F401

    assert mcp is not None
    assert isinstance(DB_PATH, Path)
    cfg = load_config()
    assert cfg.max_turns_default == 10


# ═══════════════════════════════════════════════════════════════════════════════
#  1. Memory CRUD
# ═══════════════════════════════════════════════════════════════════════════════


class TestMemoryCRUD:
    """Save → Search → List → Delete — each method tested atomically,
    then a full-cycle integration assertion."""

    def test_save_returns_positive_id(self):
        from companion.memory.store import save_memory

        mid = save_memory("fact", "Smoke test fact", "user")
        assert isinstance(mid, int)
        assert mid > 0

    def test_search_finds_saved_memory(self):
        from companion.memory.store import save_memory
        from companion.memory.context import search_memory

        save_memory("fact", "TypeScript is awesome", "project")
        results = search_memory("TypeScript")
        assert len(results) >= 1
        assert any("TypeScript" in r["content"] for r in results)

    def test_list_filters_by_scope(self):
        from companion.memory.store import save_memory
        from companion.memory.list import list_memories

        save_memory("decision", "Use pytest for tests", "project")
        results = list_memories(scope="project", limit=100)
        assert len(results) >= 1
        assert all(r["scope"] == "project" for r in results)

    def test_delete_removes_from_list(self):
        from companion.memory.store import save_memory, delete_memory
        from companion.memory.list import list_memories

        mid = save_memory("fact", "will-be-soft-deleted", "user")
        assert delete_memory(mid) is True

        after = list_memories(limit=200)
        assert not any(m["id"] == mid for m in after)

    def test_full_crud_cycle(self):
        """Save → Search → List → Delete — all four ops in sequence."""
        from companion.memory.store import save_memory, delete_memory
        from companion.memory.context import search_memory
        from companion.memory.list import list_memories

        # ── Save ──
        mid = save_memory("pattern", "Smoke CRUD cycle marker", "project")
        assert mid > 0

        # ── Search ──
        found = search_memory("Smoke CRUD")
        assert any(m["id"] == mid for m in found)

        # ── List ──
        all_mem = list_memories(scope="project", limit=200)
        assert mid in [m["id"] for m in all_mem]

        # ── Delete ──
        assert delete_memory(mid) is True
        after = list_memories(scope="project", limit=200)
        assert mid not in [m["id"] for m in after]

    def test_search_empty_query_returns_all(self):
        """Search with no query returns all memories for the scope."""
        from companion.memory.store import save_memory
        from companion.memory.context import search_memory

        save_memory("fact", "empty-query-test-A", "user")
        save_memory("fact", "empty-query-test-B", "user")
        results = search_memory(query=None, scope="user", limit=100)
        assert len(results) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Tool Call Classifier (pre-filter only — no model dispatch)
# ═══════════════════════════════════════════════════════════════════════════════


class TestClassifier:
    """Classification of known tool categories via the sub-millisecond
    pre-filter.  No DEEPSEEK_API_KEY required."""

    def test_read_tool_allowed(self):
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("Read", {"filePath": "/tmp/x"})
        assert result["decision"] == "ALLOW"
        assert "read-only" in result["reason"]

    def test_write_tool_asks_user(self):
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("Write", {"filePath": "/tmp/x", "content": "hi"})
        assert result["decision"] == "ASK_USER"
        assert "write" in result["reason"].lower()

    def test_destructive_bash_denied(self):
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("Bash", {"command": "rm -rf /"})
        assert result["decision"] == "DENY"
        assert "destructive" in result["reason"]

    def test_allowlisted_bash_allowed(self):
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("Bash", {"command": "ls -la"})
        assert result["decision"] == "ALLOW"
        assert "allowlisted" in result["reason"]

    def test_edit_tool_asks_user(self):
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("Edit", {"filePath": "/tmp/x"})
        assert result["decision"] == "ASK_USER"

    def test_empty_bash_command_denied(self):
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("Bash", {})
        assert result["decision"] == "DENY"
        assert "empty command" in result["reason"]

    def test_interactive_bash_allowed(self):
        """interactive_bash is aliased to Bash classification."""
        from companion.classifier.classifier import classify_tool_call

        result = classify_tool_call("interactive_bash", {"command": "ls"})
        assert result["decision"] == "ALLOW"


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Goal-Oriented Agent Loop
# ═══════════════════════════════════════════════════════════════════════════════


class TestGoalLoop:
    """Simulated agent loop — monkeypatched classifier per existing pattern
    in test_goal_loop.py.  Zero real model dispatch."""

    @staticmethod
    def _make_classify(decision: str = "ALLOW", reason: str = "smoke"):
        def _classify(*a: Any, **kw: Any) -> dict[str, str]:
            return {"decision": decision, "reason": reason}

        return _classify

    def test_goal_loop_completes_on_task_done(self, monkeypatch):
        from companion.goal.loop import goal_loop

        monkeypatch.setattr(
            "companion.goal.loop.classify_tool_call",
            self._make_classify("ALLOW"),
        )

        result = goal_loop(
            goal="smoke: simple completion",
            actions=[
                {"tool_name": "Read", "tool_args": {"filePath": "/tmp/x"}},
                {"tool_name": "task_done", "tool_args": {"summary": "done"}},
            ],
        )

        assert result["status"] == "goal_met"
        assert result["turns_used"] == 2
        assert result["total_cost"] > 0
        assert "task_done" in result["termination_reason"]
        assert len(result["turns"]) == 2
        assert result["turns"][1]["decision"] == "ALLOW"

    def test_goal_loop_blocked_after_three_denials(self, monkeypatch):
        from companion.goal.loop import goal_loop

        monkeypatch.setattr(
            "companion.goal.loop.classify_tool_call",
            self._make_classify("DENY", "blocked-by-smoke"),
        )

        result = goal_loop(
            goal="smoke: blocked",
            max_turns=10,
            actions=[
                {"tool_name": "Bash", "tool_args": {"command": "nope"}},
                {"tool_name": "Bash", "tool_args": {"command": "nope"}},
                {"tool_name": "Bash", "tool_args": {"command": "nope"}},
            ],
        )

        assert result["status"] == "blocked"
        assert result["turns_used"] == 3
        assert "3 consecutive DENY" in result["termination_reason"]

    def test_goal_loop_cost_exceeded(self, monkeypatch):
        from companion.goal.loop import goal_loop

        monkeypatch.setattr(
            "companion.goal.loop.classify_tool_call",
            self._make_classify("ALLOW"),
        )

        result = goal_loop(
            goal="smoke: cost exceeded",
            cost_ceiling=1.00,
            max_turns=5,
            actions=[
                {
                    "tool_name": "Bash",
                    "tool_args": {"command": "ls"},
                    "estimated_cost": 5.00,
                },
            ],
        )

        assert result["status"] == "cost_exceeded"
        assert result["turns_used"] == 1
        assert "exceeds ceiling" in result["termination_reason"]

    def test_goal_loop_output_summary_fields_present(self, monkeypatch):
        from companion.goal.loop import goal_loop

        monkeypatch.setattr(
            "companion.goal.loop.classify_tool_call",
            self._make_classify("ALLOW"),
        )

        result = goal_loop(
            goal="smoke: summary check",
            actions=[
                {"tool_name": "Read", "tool_args": {"filePath": "/tmp/x"}},
                {"tool_name": "task_done", "tool_args": {"summary": "ok"}},
            ],
        )

        for key in (
            "goal",
            "status",
            "turns_used",
            "total_cost",
            "wall_time_ms",
            "output_summary",
            "termination_reason",
            "turns",
        ):
            assert key in result, f"Missing key: {key}"


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Skill Bridge
# ═══════════════════════════════════════════════════════════════════════════════


class TestSkillBridge:
    """Load a verified skill (caveman) from the real workspace and verify
    the loader resolves frontmatter + body correctly."""

    def test_skill_load_caveman_returns_resolved_body(self):
        from companion.skill.loader import load_skill

        # The caveman skill lives at .agents/skills/caveman/SKILL.md
        # relative to the repo root.  Smoke tests are expected to be
        # executed from the repo root so that relative search paths
        # resolve correctly.
        try:
            result = load_skill("caveman")
        except FileNotFoundError:
            # If not at repo root, try absolute path resolution
            candidate = _REPO_ROOT / ".agents" / "skills" / "caveman" / "SKILL.md"
            if not candidate.exists():
                pytest.skip(f"caveman SKILL.md not found at {candidate}")
            raise

        assert result["name"] == "caveman"
        assert "resolved_body" in result
        assert "frontmatter" in result
        assert "warnings" in result

        # caveman frontmatter should have name + description
        fm = result["frontmatter"]
        assert fm.get("name") == "caveman"

        # body must be non-empty
        body = result["resolved_body"]
        assert len(body) > 50
        assert isinstance(body, str)

    def test_skill_load_caveman_body_contains_expected_content(self):
        from companion.skill.loader import load_skill

        try:
            result = load_skill("caveman")
        except FileNotFoundError:
            candidate = _REPO_ROOT / ".agents" / "skills" / "caveman" / "SKILL.md"
            if not candidate.exists():
                pytest.skip(f"caveman SKILL.md not found at {candidate}")
            raise

        body = result["resolved_body"]
        # caveman skill is a communication mode — should mention token reduction
        assert (
            "token" in body.lower()
            or "caveman" in body.lower()
            or "communication" in body.lower()
        ), f"Unexpected caveman body content: {body[:200]}"

    def test_skill_load_nonexistent_raises(self):
        from companion.skill.loader import load_skill

        with pytest.raises(FileNotFoundError):
            load_skill("definitely-does-not-exist-xyzzy")


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Permission Audit (config_migrate)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPermissionAudit:
    """Read-only config migration — writes a temp settings.json, runs
    config_migrate, checks output."""

    def test_config_migrate_produces_output(self):
        from companion.permission.migrate import config_migrate

        # Create a minimal Claude Code settings file
        settings: dict[str, Any] = {
            "permissions": {
                "allow": ["Read", "Glob", "Grep"],
                "deny": ["Bash(rm:*)", "Write(/etc/*)"],
            },
            "model": "sonnet",
            "browser": True,
            "verbose": False,
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(settings, f)
            tmp_path = f.name

        try:
            output = config_migrate(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert len(output) > 0
        assert "Migration from Claude Code settings" in output
        assert "Permissions" in output
        assert "Read" in output
        # model "sonnet" should map to "deepseek-v4-flash"
        assert "deepseek-v4-flash" in output
        assert "sonnet" in output  # source annotation

    def test_config_migrate_missing_file_graceful(self):
        from companion.permission.migrate import config_migrate

        output = config_migrate("/nonexistent/path/settings.json")
        assert "No Claude Code config found" in output

    def test_config_migrate_filters_secrets(self):
        from companion.permission.migrate import config_migrate

        settings: dict[str, Any] = {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "sk-ant-secret-token-that-is-long-enough",
                "HOME": "/home/user",
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(settings, f)
            tmp_path = f.name

        try:
            output = config_migrate(tmp_path)
        finally:
            os.unlink(tmp_path)

        assert "FILTERED" in output
        assert "ANTHROPIC_AUTH_TOKEN" in output
        # home should not be filtered (not a secret)
        assert "HOME" in output


# ═══════════════════════════════════════════════════════════════════════════════
#  6. Model Fusion (built-in mock dispatch)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFusionDispatch:
    """fusion_dispatch uses a built-in mock — no real API calls, but all
    the threading/cost/synthesis logic runs for real."""

    def test_fusion_dispatch_returns_dict_with_expected_keys(self):
        from companion.fusion.dispatch import fusion_dispatch

        result = fusion_dispatch(
            prompt="What is 2 + 2?",
            models=["deepseek-v4-pro", "deepseek-v4-flash"],
            cost_ceiling=5.00,
            timeout_per_model=30,
        )

        for key in (
            "prompt",
            "model_responses",
            "fused_answer",
            "cost",
            "wall_time_ms",
            "timed_out_models",
            "label",
        ):
            assert key in result, f"Missing key: {key}"

    def test_fusion_dispatch_label_is_experimental(self):
        from companion.fusion.dispatch import fusion_dispatch

        result = fusion_dispatch(
            prompt="smoke fusion test",
            models=["deepseek-v4-pro", "deepseek-v4-flash"],
            timeout_per_model=30,
        )

        assert "EXPERIMENTAL" in result["label"]
        assert "EXPERIMENTAL" in result["fused_answer"]

    def test_fusion_dispatch_empty_prompt_raises(self):
        from companion.fusion.dispatch import fusion_dispatch

        with pytest.raises(ValueError, match="non-empty prompt"):
            fusion_dispatch(prompt="   ")


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Feedback Logging & Learned Rules
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeedbackAndLearning:
    """log_override → writes feedback; after 5 consistent overrides →
    check_learned_rules creates a pending-review rule."""

    def test_log_override_returns_row_id(self):
        from companion.classifier.feedback import log_override

        row_id = log_override(
            tool_name="Write",
            tool_args_short="file: /tmp/x",
            classifier_decision="DENY",
            user_override="ALLOW",
            session_id="smoke-session",
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_five_consistent_overrides_creates_learned_rule(self):
        from companion.classifier.feedback import log_override, check_learned_rules

        tool_name = "Bash-smoke-test"
        for _ in range(5):
            log_override(
                tool_name=tool_name,
                tool_args_short="rm cache",
                classifier_decision="DENY",
                user_override="ALLOW",
                session_id="smoke-learn",
            )

        rules = check_learned_rules()
        # At least one rule should match our pattern
        matching = [r for r in rules if r["tool_pattern"] == tool_name]
        if not matching:
            # check_learned_rules may have already seen this pattern from
            # prior runs; query the DB directly to confirm it was stored
            from companion.db import get_db

            with get_db() as db:
                row = db.execute(
                    "SELECT * FROM learned_rules WHERE tool_pattern = ?",
                    (tool_name,),
                ).fetchone()
                assert row is not None, (
                    f"Expected learned rule for {tool_name} in DB"
                )
                assert row["learned_decision"] == "ALLOW"
                assert row["status"] == "pending_review"
                assert row["override_count"] >= 5
        else:
            rule = matching[0]
            assert rule["learned_decision"] == "ALLOW"
            assert rule["status"] == "pending_review"
            assert rule["override_count"] >= 5

    def test_ask_user_overrides_are_not_learnable(self):
        """ASK_USER overrides are explicitly excluded from learning."""
        from companion.classifier.feedback import log_override, check_learned_rules

        # We check that ASK_USER overrides don't generate a rule,
        # even with 5 iterations.
        tool_name = "AskUser-smoke-nolearn"
        for _ in range(5):
            log_override(
                tool_name=tool_name,
                tool_args_short="some args",
                classifier_decision="DENY",
                user_override="ASK_USER",
                session_id="smoke-no-learn",
            )

        rules = check_learned_rules()
        matching = [r for r in rules if r["tool_pattern"] == tool_name]
        assert len(matching) == 0, (
            f"ASK_USER override should NOT create a learned rule for {tool_name}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Plugin TypeScript compilation (optional — requires npm deps)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPluginTypeScript:
    """Only executed when node_modules are present."""

    @pytest.mark.skipif(
        not (_COMPANION_ROOT / "plugin" / "node_modules" / ".package-lock.json").exists(),
        reason="plugin node_modules not installed — run `npm install` in bifrost/plugin",
    )
    def test_typescript_compiles(self):
        """Run ``npx tsc --noEmit`` in the plugin directory."""
        plugin_dir = _COMPANION_ROOT / "plugin"
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(plugin_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            pytest.fail(
                f"TypeScript compilation failed:\nSTDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
