"""Feedback logging and experimental learning for the tool-call classifier.

When a user overrides a classifier decision, ``log_override`` records the
event in ``classifier_feedback``.  Once the same ``(tool_name, user_override)``
combo accumulates **5 consistent overrides**, ``check_learned_rules``
creates a ``learned_rules`` row with ``status='pending_review'``.

Learned rules are **never** auto-applied — a human must review and promote
them to ``active`` before the classifier consumes them.
"""

from __future__ import annotations

from typing import Any

from companion.db import get_db

# ──────────────────────────────────────────────────────────────────────
#  Constraints
# ──────────────────────────────────────────────────────────────────────

_MAX_ARGS_LEN: int = 200         # truncate tool_args_short to this length
_MIN_OVERRIDE_COUNT: int = 5     # overrides needed before a rule is learned
_LEARNABLE_DECISIONS: frozenset[str] = frozenset({"ALLOW", "DENY"})

# ──────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────


def log_override(
    tool_name: str,
    tool_args_short: str,
    classifier_decision: str,
    user_override: str,
    session_id: str = "",
) -> int:
    """Record a user override of a classifier decision.

    Parameters
    ----------
    tool_name:
        Name of the tool that was classified (e.g. ``"Bash"``, ``"Write"``).
    tool_args_short:
        Safe truncated summary of the tool arguments (max 200 chars).
    classifier_decision:
        The original decision made by the classifier (``ALLOW``, ``DENY``,
        or ``ASK_USER``).
    user_override:
        The decision the user chose instead (``ALLOW`` or ``DENY``).
        ASK_USER overrides are **not** learnable.
    session_id:
        Optional session identifier for traceability.

    Returns
    -------
    int
        The ``id`` of the inserted ``classifier_feedback`` row.
    """
    truncated_args = tool_args_short[:_MAX_ARGS_LEN]

    with get_db() as db:
        cursor = db.execute(
            """INSERT INTO classifier_feedback
               (tool_name, tool_args_short, decision, user_override, session_id)
               VALUES (?, ?, ?, ?, ?)""",
            (tool_name, truncated_args, classifier_decision, user_override, session_id or ""),
        )
        row_id = cursor.lastrowid
        db.commit()

    # Check for new learned rules after every logged override so the
    # feedback→rule cycle stays self-contained.
    check_learned_rules()

    return row_id


def check_learned_rules() -> list[dict[str, Any]]:
    """Scan ``classifier_feedback`` for combos that have reached the
    override threshold and create pending-review learned rules.

    Only ``ALLOW`` and ``DENY`` overrides are considered (``ASK_USER``
    is explicitly excluded).  Each unique ``(tool_name, user_override)``
    combo with **≥ 5** feedback rows becomes a learned rule candidate.

    Rows already present in ``learned_rules`` (matched on ``tool_pattern``
    + ``learned_decision``) are **skipped** to avoid duplicates.

    Returns
    -------
    list[dict]
        Newly created rules, each with keys ``tool_pattern``,
        ``learned_decision``, ``override_count``, and ``status``.
    """
    new_rules: list[dict[str, Any]] = []

    with get_db() as db:
        # Find (tool_name, user_override) combos with >= 5 overrides.
        # Exclude ASK_USER — the classifier already defaults to it.
        rows = db.execute(
            """SELECT tool_name,
                      user_override,
                      COUNT(*) AS cnt
               FROM classifier_feedback
               WHERE user_override IN ('ALLOW', 'DENY')
               GROUP BY tool_name, user_override
               HAVING cnt >= ?""",
            (_MIN_OVERRIDE_COUNT,),
        ).fetchall()

        for row in rows:
            pattern = row["tool_name"]
            learned_decision = row["user_override"]
            count = row["cnt"]

            # Deduplicate: skip if (tool_pattern, learned_decision) exists.
            existing = db.execute(
                """SELECT id FROM learned_rules
                   WHERE tool_pattern = ? AND learned_decision = ?""",
                (pattern, learned_decision),
            ).fetchone()

            if existing is not None:
                continue

            db.execute(
                """INSERT INTO learned_rules
                   (tool_pattern, learned_decision, override_count, status)
                   VALUES (?, ?, ?, 'pending_review')""",
                (pattern, learned_decision, count),
            )
            new_rules.append({
                "tool_pattern": pattern,
                "learned_decision": learned_decision,
                "override_count": count,
                "status": "pending_review",
            })

        db.commit()

    return new_rules
