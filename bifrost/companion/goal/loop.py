"""Goal-oriented agent loop with classifier-driven safety gating.

Each turn of the loop simulates an agent action: the action is passed
through the security classifier, its decision is recorded, and
cumulative metrics (cost, denial streak) are tracked.  The loop
terminates on one of four conditions:

* **goal_met** — a ``task_done`` action is encountered.
* **max_turns** — the configured turn budget is exhausted.
* **cost_exceeded** — cumulative estimated cost exceeds the ceiling.
* **blocked** — three consecutive DENY decisions from the classifier.

The loop is designed for *simulation* — real agent execution is
outside scope.  Callers pass a list of ``actions`` dicts that
describe the tool calls the agent would have made.
"""

from __future__ import annotations

import time
from typing import Any

from companion.classifier.classifier import classify_tool_call
from companion.config import load_config

# ── Terminal tool names ────────────────────────────────────────────────────

_TERMINAL_TOOLS: frozenset[str] = frozenset({"task_done", "task_complete", "finish"})

# ── Constants ───────────────────────────────────────────────────────────────

_MAX_TURNS_ABSOLUTE = 50
_DEFAULT_ESTIMATED_COST = 0.01

# ── Helpers ─────────────────────────────────────────────────────────────────


def _validate_args(
    goal: str,
    max_turns: int,
    cost_ceiling: float,
    auto_mode: bool,
    actions: list[dict[str, Any]],
) -> None:
    """Validate goal_loop arguments, raising ``ValueError`` on violations."""
    if not goal.strip():
        raise ValueError("goal must be a non-empty string")
    if len(goal) > 2000:
        raise ValueError("goal must be ≤ 2000 characters")
    if max_turns < 1:
        raise ValueError("max_turns must be ≥ 1")
    if max_turns > _MAX_TURNS_ABSOLUTE:
        raise ValueError(f"max_turns must be ≤ {_MAX_TURNS_ABSOLUTE}")
    if cost_ceiling <= 0:
        raise ValueError("cost_ceiling must be > 0")
    if not isinstance(actions, list):
        raise ValueError("actions must be a list of dicts")
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{i}] must be a dict, got {type(action).__name__}")
        if "tool_name" not in action:
            raise ValueError(f"actions[{i}] missing required key 'tool_name'")


def _estimate_cost(action: dict[str, Any]) -> float:
    """Return the estimated cost for a single action.

    Uses the action's ``estimated_cost`` field if present; otherwise
    falls back to a conservative default.
    """
    cost = action.get("estimated_cost", _DEFAULT_ESTIMATED_COST)
    if not isinstance(cost, (int, float)) or cost < 0:
        return _DEFAULT_ESTIMATED_COST
    return float(cost)


# ── Public API ──────────────────────────────────────────────────────────────


def goal_loop(
    goal: str,
    max_turns: int = 10,
    cost_ceiling: float = 1.00,
    auto_mode: bool = False,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a classifier-gated goal-oriented agent loop (simulation).

    Parameters
    ----------
    goal:
        Human-readable description of the task the agent is pursuing.
    max_turns:
        Maximum number of turns (actions) before forced termination.
        Clamped to 50 (absolute cap).
    cost_ceiling:
        Dollar ceiling for cumulative estimated cost.  When the
        running total exceeds this value the loop terminates with
        ``status="cost_exceeded"``.
    auto_mode:
        Reserved for future auto-approval.  Currently unused.
    actions:
        List of simulated agent actions.  Each dict must contain at
        least ``tool_name`` (str).  Optional keys: ``tool_args``
        (dict), ``estimated_cost`` (float, default 0.01),
        ``file_paths`` (list[str]).

    Returns
    -------
    dict
        Summary with keys:

        * ``goal`` — the input goal string
        * ``status`` — ``"goal_met"`` | ``"max_turns"`` | ``"cost_exceeded"`` | ``"blocked"``
        * ``turns_used`` — number of turns executed
        * ``total_cost`` — cumulative estimated cost in dollars
        * ``wall_time_ms`` — elapsed wall-clock time in milliseconds
        * ``output_summary`` — human-readable summary of the outcome
        * ``termination_reason`` — why the loop stopped
        * ``turns`` — list of per-turn records (turn_index, tool_name,
          decision, reason, estimated_cost, cumulative_cost)
    """
    t0 = time.perf_counter()

    actions = actions or []

    # Load config defaults, overridden by explicit args
    cfg = load_config()
    if max_turns == 10:  # user did not override — use config default
        max_turns = cfg.max_turns_default
    if cost_ceiling == 1.00:
        cost_ceiling = cfg.cost_ceiling_default

    _validate_args(goal, max_turns, cost_ceiling, auto_mode, actions)

    # ── state ──────────────────────────────────────────────────────────
    cumulative_cost = 0.0
    consecutive_denials = 0
    turns_executed = 0
    turn_records: list[dict[str, Any]] = []
    termination_reason = ""
    status = "max_turns"  # default fallback

    session_context: dict[str, Any] = {"goal": goal, "task_id": "goal_loop"}

    # ── main loop ──────────────────────────────────────────────────────
    for i, action in enumerate(actions):
        if turns_executed >= max_turns:
            termination_reason = f"reached max_turns ({max_turns})"
            status = "max_turns"
            break

        tool_name: str = action.get("tool_name", "unknown")
        tool_args: dict[str, Any] = action.get("tool_args", {})
        file_paths: list[str] | None = action.get("file_paths")
        estimated_cost = _estimate_cost(action)

        # ── classify ───────────────────────────────────────────────
        decision = classify_tool_call(
            tool_name=tool_name,
            tool_args=tool_args,
            file_paths=file_paths,
            session_context=session_context,
        )
        decision_str: str = decision.get("decision", "ASK_USER")
        reason: str = decision.get("reason", "")

        # ── track cost ─────────────────────────────────────────────
        cumulative_cost += estimated_cost

        # ── track denials ──────────────────────────────────────────
        if decision_str == "DENY":
            consecutive_denials += 1
        else:
            consecutive_denials = 0

        # ── record turn ────────────────────────────────────────────
        turn_records.append(
            {
                "turn_index": turns_executed,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "decision": decision_str,
                "reason": reason,
                "estimated_cost": estimated_cost,
                "cumulative_cost": round(cumulative_cost, 4),
            }
        )
        turns_executed += 1

        # ── termination checks (in priority order) ─────────────────
        # 1. Goal achieved — task_done action
        if tool_name in _TERMINAL_TOOLS:
            termination_reason = f"goal met via {tool_name}"
            status = "goal_met"
            break

        # 2. Blocked — 3 consecutive DENY
        if consecutive_denials >= 3:
            termination_reason = "3 consecutive DENY decisions from classifier"
            status = "blocked"
            break

        # 3. Cost exceeded
        if cumulative_cost > cost_ceiling:
            termination_reason = (
                f"cumulative cost ${cumulative_cost:.4f} "
                f"exceeds ceiling ${cost_ceiling:.2f}"
            )
            status = "cost_exceeded"
            break

    # ── post-loop: final termination check ──────────────────────────────
    if not termination_reason:
        # Loop exhausted all actions without hitting any termination condition
        termination_reason = f"reached max_turns ({max_turns})"
        status = "max_turns"

    wall_time_ms = int((time.perf_counter() - t0) * 1000)

    # ── build output summary ────────────────────────────────────────────
    output_summary = (
        f"GoalLoop completed: status={status}, "
        f"turns={turns_executed}/{max_turns}, "
        f"cost=${cumulative_cost:.4f}/{cost_ceiling:.2f}, "
        f"wall={wall_time_ms}ms"
    )

    return {
        "goal": goal,
        "status": status,
        "turns_used": turns_executed,
        "total_cost": round(cumulative_cost, 4),
        "wall_time_ms": wall_time_ms,
        "output_summary": output_summary,
        "termination_reason": termination_reason,
        "turns": turn_records,
    }
