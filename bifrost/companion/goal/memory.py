"""Goal-loop memory reporting.

At goal-loop completion, saves 2 memory entries:
1. **decision** — goal + outcome + turns used
2. **pattern** — any learned patterns from the loop

Also saves intermediate progress every 3 turns as a decision memory with
``status='in_progress'``.  One-turn loops are never persisted — they are
considered trivial and produce no learnable signal.
"""

from __future__ import annotations

from typing import Any

from companion.memory.scope import get_project_hash
from companion.memory.store import save_memory

_SCOPE = "project"
_MAX_CONTENT_CHARS = 1000


# ── helpers ──────────────────────────────────────────────────────────────────


def _truncate(content: str, max_chars: int = _MAX_CONTENT_CHARS) -> str:
    """Truncate *content* to *max_chars*, appending ``"…"`` when trimmed."""
    if len(content) > max_chars:
        return content[: max_chars - 1] + "…"
    return content


def _format_decision_content(goal_result: dict[str, Any]) -> str:
    """Build the final decision memory body from a goal-loop result."""
    return (
        f"Goal: {goal_result['goal']}\n"
        f"Status: {goal_result['status']}\n"
        f"Turns used: {goal_result['turns_used']}\n"
        f"Termination: {goal_result['termination_reason']}\n"
        f"Total cost: ${goal_result['total_cost']:.4f}"
    )


def _extract_patterns(goal_result: dict[str, Any]) -> str:
    """Derive observable patterns from the per-turn records."""
    turns: list[dict[str, Any]] = goal_result.get("turns", [])
    if not turns:
        return "No turn data available for pattern extraction."

    tools: dict[str, int] = {}
    decisions: dict[str, int] = {}
    denial_streaks: list[int] = []
    current_streak = 0

    for turn in turns:
        tool = turn.get("tool_name", "unknown")
        decision = turn.get("decision", "ASK_USER")

        tools[tool] = tools.get(tool, 0) + 1
        decisions[decision] = decisions.get(decision, 0) + 1

        if decision == "DENY":
            current_streak += 1
        else:
            if current_streak > 0:
                denial_streaks.append(current_streak)
            current_streak = 0

    if current_streak > 0:
        denial_streaks.append(current_streak)

    lines: list[str] = []

    # Top 5 tools by usage
    top_tools = sorted(tools.items(), key=lambda kv: -kv[1])[:5]
    lines.append(
        "Tool usage: "
        + ", ".join(f"{name}({count})" for name, count in top_tools)
    )

    # Decision distribution
    dist_parts = []
    for label in ("ALLOW", "DENY", "ASK_USER"):
        if label in decisions:
            dist_parts.append(f"{label}={decisions[label]}")
    lines.append("Decisions: " + ", ".join(dist_parts))

    if denial_streaks:
        max_streak = max(denial_streaks)
        lines.append(
            f"Denial streaks: {denial_streaks} (max streak: {max_streak})"
        )
    else:
        lines.append("No denial streaks detected.")

    lines.append(f"Total turns: {goal_result['turns_used']}")

    return "\n".join(lines)


# ── public API ───────────────────────────────────────────────────────────────


def report_goal_completion(goal_result: dict[str, Any]) -> tuple[int, int]:
    """Persist memory entries for a completed goal loop.

    Parameters
    ----------
    goal_result:
        The dict returned by :func:`~companion.goal.loop.goal_loop`.

    Returns
    -------
    tuple[int, int]
        ``(final_memory_id, pattern_memory_id)``.  When *turns_used* ≤ 1
        both values are 0 — no memories are saved for trivial loops.
    """
    turns_used: int = goal_result.get("turns_used", 0)
    turns: list[dict[str, Any]] = goal_result.get("turns", [])

    if turns_used <= 1:
        return (0, 0)

    project_hash = get_project_hash()

    # ── intermediate progress saves (every 3 turns, starting at turn 3) ──
    for turn in turns:
        turn_number = turn["turn_index"] + 1
        if turn_number % 3 == 0 and turn_number > 1:
            content = (
                f"Goal: {goal_result['goal']}\n"
                f"Turn: {turn_number}/{turns_used} "
                f"Status: in_progress\n"
                f"Tool: {turn['tool_name']} "
                f"Decision: {turn['decision']}"
            )
            save_memory("decision", _truncate(content), _SCOPE, project_hash)

    # ── final decision memory ─────────────────────────────────────────────
    decision_content = _truncate(_format_decision_content(goal_result))
    final_id = save_memory("decision", decision_content, _SCOPE, project_hash)

    # ── pattern memory ────────────────────────────────────────────────────
    pattern_content = _truncate(_extract_patterns(goal_result))
    pattern_id = save_memory("pattern", pattern_content, _SCOPE, project_hash)

    return (final_id, pattern_id)
