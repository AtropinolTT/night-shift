"""Goal loop integration tests (T6.4).

Verifies three goal-loop termination scenarios plus memory reporting:
1. Simple goal — ``task_done`` → ``status='goal_met'``
2. Blocked goal — 3 consecutive DENY → ``status='blocked'``
3. Budget exceeded — high-cost action → ``status='cost_exceeded'``
4. Memory reporting — ``report_goal_completion`` persists memories

All tests monkeypatch ``companion.goal.loop.classify_tool_call`` so
zero real model dispatch occurs.  Total runtime < 5 s.
"""

from __future__ import annotations

from companion.db import get_db
from companion.goal.loop import goal_loop
from companion.goal.memory import report_goal_completion

# ═══════════════════════════════════════════════════════════════════════════
#  Mock helpers
# ═══════════════════════════════════════════════════════════════════════════


def _mock_classify(decision: str, reason: str = "test-mock"):
    """Return a ``classify_tool_call`` replacement that always yields *decision*."""

    def _classify(tool_name, tool_args, file_paths=None, session_context=None):
        return {"decision": decision, "reason": reason}

    return _classify


# ═══════════════════════════════════════════════════════════════════════════
#  Test 1 — Simple goal completes
# ═══════════════════════════════════════════════════════════════════════════


def test_simple_goal_completes(monkeypatch):
    """Single ``task_done`` action → ``status='goal_met'`` with 1 turn."""
    monkeypatch.setattr(
        "companion.goal.loop.classify_tool_call",
        _mock_classify("ALLOW"),
    )

    actions: list[dict] = [
        {
            "tool_name": "task_done",
            "tool_args": {"summary": "all done"},
            "estimated_cost": 0.01,
        },
    ]

    result = goal_loop(goal="test simple goal", actions=actions)

    assert result["status"] == "goal_met"
    assert result["turns_used"] == 1
    assert result["total_cost"] == 0.01
    assert result["goal"] == "test simple goal"
    assert "task_done" in result["termination_reason"]
    assert len(result["turns"]) == 1
    assert result["turns"][0]["decision"] == "ALLOW"
    assert result["turns"][0]["tool_name"] == "task_done"


# ═══════════════════════════════════════════════════════════════════════════
#  Test 2 — All DENY → blocked
# ═══════════════════════════════════════════════════════════════════════════


def test_all_deny_blocked(monkeypatch):
    """Three consecutive DENY decisions → ``status='blocked'`` after turn 3."""
    monkeypatch.setattr(
        "companion.goal.loop.classify_tool_call",
        _mock_classify("DENY", "blocked by policy"),
    )

    actions: list[dict] = [
        {"tool_name": "Bash", "tool_args": {"command": "deleted"}, "estimated_cost": 0.01},
        {"tool_name": "Bash", "tool_args": {"command": "deleted"}, "estimated_cost": 0.01},
        {"tool_name": "Bash", "tool_args": {"command": "deleted"}, "estimated_cost": 0.01},
    ]

    result = goal_loop(goal="test blocked goal", actions=actions, max_turns=10)

    assert result["status"] == "blocked"
    assert result["turns_used"] == 3
    assert "3 consecutive DENY" in result["termination_reason"]
    for turn in result["turns"]:
        assert turn["decision"] == "DENY"
        assert turn["tool_name"] == "Bash"


# ═══════════════════════════════════════════════════════════════════════════
#  Test 3 — Budget exceeded
# ═══════════════════════════════════════════════════════════════════════════


def test_budget_exceeded(monkeypatch):
    """Single action with cost >> ceiling → ``status='cost_exceeded'``."""
    monkeypatch.setattr(
        "companion.goal.loop.classify_tool_call",
        _mock_classify("ALLOW"),
    )

    actions: list[dict] = [
        {"tool_name": "Bash", "tool_args": {"command": "ls"}, "estimated_cost": 5.00},
    ]

    result = goal_loop(
        goal="test budget exceeded",
        actions=actions,
        cost_ceiling=1.00,
        max_turns=5,
    )

    assert result["status"] == "cost_exceeded"
    assert result["turns_used"] == 1
    assert result["total_cost"] == 5.00
    assert "exceeds ceiling" in result["termination_reason"]
    assert "$5.0000" in result["termination_reason"]


# ═══════════════════════════════════════════════════════════════════════════
#  Test 4 — Memory reporting
# ═══════════════════════════════════════════════════════════════════════════


def test_report_goal_completion_saves_memories(monkeypatch):
    """Multi-turn loop → intermediate + final decision + pattern memories."""
    monkeypatch.setattr(
        "companion.goal.loop.classify_tool_call",
        _mock_classify("ALLOW"),
    )

    actions: list[dict] = [
        {"tool_name": "Read", "tool_args": {"filePath": "/tmp/x"}, "estimated_cost": 0.01},
        {"tool_name": "Grep", "tool_args": {"pattern": "foo"}, "estimated_cost": 0.01},
        {"tool_name": "task_done", "tool_args": {"summary": "done"}, "estimated_cost": 0.01},
    ]

    result = goal_loop(goal="test memory reporting", actions=actions)
    assert result["status"] == "goal_met"
    assert result["turns_used"] == 3

    final_id, pattern_id = report_goal_completion(result)

    # Both IDs should be positive integers (real DB row IDs)
    assert final_id > 0
    assert pattern_id > 0

    # Verify contents persisted in the temp DB
    with get_db() as db:
        decisions = db.execute(
            "SELECT content FROM memories WHERE type='decision' AND scope='project'"
            " ORDER BY id"
        ).fetchall()
        patterns = db.execute(
            "SELECT content FROM memories WHERE type='pattern' AND scope='project'"
            " ORDER BY id"
        ).fetchall()

    # At minimum: intermediate save (turn 3) + final decision
    assert len(decisions) >= 2
    assert len(patterns) >= 1

    # Final decision memory contains goal metadata
    final_content = decisions[-1]["content"]
    assert "test memory reporting" in final_content
    assert "goal_met" in final_content
    assert "3" in final_content  # turns_used

    # Pattern memory contains tool-frequency data
    pattern_content = patterns[-1]["content"]
    assert "Read" in pattern_content or "Grep" in pattern_content
    assert "Total turns: 3" in pattern_content


def test_report_goal_completion_skips_trivial_loop(monkeypatch):
    """``turns_used ≤ 1`` → no memories saved, returns ``(0, 0)``."""
    monkeypatch.setattr(
        "companion.goal.loop.classify_tool_call",
        _mock_classify("ALLOW"),
    )

    actions: list[dict] = [
        {"tool_name": "task_done", "tool_args": {}, "estimated_cost": 0.01},
    ]

    result = goal_loop(goal="trivial goal", actions=actions)
    assert result["turns_used"] <= 1

    final_id, pattern_id = report_goal_completion(result)
    assert final_id == 0
    assert pattern_id == 0
