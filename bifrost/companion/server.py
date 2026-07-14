"""Bifrost companion — FastMCP server for the Bifrost OpenCode plugin."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Ensure the companion package is importable regardless of working directory.
# When OpenCode spawns `python3 /path/to/bifrost/companion/server.py`, the cwd
# is arbitrary — without this, `from companion.xxx import ...` raises
# ModuleNotFoundError and the process exits immediately, causing MCP error
# -32000: Connection closed.
_SELF_DIR = Path(__file__).resolve().parent
if str(_SELF_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SELF_DIR.parent))

# ── NFS bytecode cache mitigation ───────────────────────────
# NFS timestamps may not update reliably, causing Python to use
# stale .pyc files. Delete __pycache__ dirs + invalidate caches.
import importlib
import shutil
for pycache in _SELF_DIR.parent.rglob("__pycache__"):
    try:
        shutil.rmtree(pycache)
    except OSError:
        pass
importlib.invalidate_caches()

from fastmcp import FastMCP

from companion.classifier.classifier import classify_tool_call as _classify_tool_call
from companion.classifier.feedback import log_override as _log_override
from companion.cost.tracker import SessionCostTracker
from companion.goal.loop import goal_loop as _goal_loop
from companion.memory.list import list_memories
from companion.memory.store import save_memory, delete_memory
from companion.memory.context import search_memory
from companion.permission.migrate import config_migrate as _config_migrate
from companion.skill.loader import (
    _parse_frontmatter,
    load_skill,
)
from companion.utils.tokenizer import count_tokens as _count_tokens

mcp = FastMCP("bifrost-companion")

# ── session cost tracker ─────────────────────────────────────────────────
_cost_tracker = SessionCostTracker()

# ── skill discovery ───────────────────────────────────────────────────────

SKILL_SEARCH_PATHS: list[Path] = [
    Path(".agents/skills"),                      # project-level (highest priority)
    Path.home() / ".claude" / "skills",          # user-level
    Path(".claude/skills"),                      # repo-level (fallback)
]

_COMPAT_MD_PATH = Path(__file__).parent.parent / "SKILL_COMPAT.md"


def _parse_compat_status() -> dict[str, str]:
    """Parse SKILL_COMPAT.md → {skill_name: 'verified'|'best_effort'}."""
    statuses: dict[str, str] = {}
    if not _COMPAT_MD_PATH.exists():
        return statuses

    text = _COMPAT_MD_PATH.read_text(encoding="utf-8")

    # Verified table: "| N | `name` | ... | ✅ Verified |"
    for m in re.finditer(
        r"\|\s*\d+\s*\|\s*`([^`]+)`\s*\|.*?\|\s*✅ Verified\s*\|", text
    ):
        statuses[m.group(1)] = "verified"

    # Best-effort sections: "| `name` | ... | Not verified |"
    for m in re.finditer(r"\|\s*`([^`]+)`\s*\|.*?\|\s*Not verified\s*\|", text):
        if m.group(1) not in statuses:
            statuses[m.group(1)] = "best_effort"

    return statuses


def _scan_skills(cwd: Path | None = None) -> list[dict[str, Any]]:
    """Discover skills across all search paths.  Project skills take priority."""
    root = cwd or Path.cwd()
    compat = _parse_compat_status()
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    for base in SKILL_SEARCH_PATHS:
        base = base if base.is_absolute() else root / base
        if not base.is_dir():
            continue
        for skill_dir in sorted(base.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            name = skill_dir.name
            # Project-level (.agents/) takes priority over user-level
            if name in seen:
                continue
            seen.add(name)

            try:
                raw = skill_md.read_text(encoding="utf-8")
                frontmatter, _ = _parse_frontmatter(raw)
            except Exception:
                frontmatter = {}

            results.append({
                "name": frontmatter.get("name", name),
                "description": frontmatter.get("description", ""),
                "path": str(skill_dir),
                "compatibility": compat.get(name, "unknown"),
            })

    return results


@mcp.tool()
def echo(message: str) -> Any:
    try:
        return message
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def version() -> Any:
    try:
        return "bifrost v0.2.1"
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def memory_save(type: str, content: str, scope: str = "user", project_hash: str = "") -> Any:
    try:
        id_ = save_memory(type, content, scope, project_hash or None)
        return f"saved {id_}"
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def memory_search(
    query: str = "",
    scope: str | None = None,
    type_filter: str | None = None,
    limit: int = 10,
) -> Any:
    try:
        type_list = [t.strip() for t in type_filter.split(",") if t.strip()] if type_filter else None
        return search_memory(query or None, scope, type_list, limit)
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def memory_delete(memory_id: int) -> Any:
    try:
        delete_memory(memory_id)
        return "deleted"
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def memory_list(
    scope: str | None = None,
    type_filter: str | None = None,
    limit: int = 50,
) -> Any:
    try:
        return list_memories(scope, type_filter, limit)
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def classify_tool_call(
    tool_name: str,
    tool_args: dict[str, Any] | None = None,
    file_paths: list[str] | None = None,
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a tool call with DEFAULT DENY policy.

    Returns {"decision": "ALLOW"|"DENY"|"ASK_USER", "reason": "..."}.
    Uses a two-tier architecture: pre-filter (~0ms fast-path) for known
    tool categories, then cheap-model dispatch for ambiguous calls.
    Falls back to ASK_USER on any failure.
    """
    tool_args = tool_args or {}
    try:
        return _classify_tool_call(tool_name, tool_args, file_paths, session_context)
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def log_override(
    tool_name: str,
    tool_args_short: str,
    classifier_decision: str,
    user_override: str,
    session_id: str = "",
) -> Any:
    """Log a user override of a classifier decision and check for learned rules.

    Records the override in classifier_feedback.  After 5 consistent overrides
    for the same tool+decision, a learned_rules row is created with
    status='pending_review'.  Learned rules are NEVER auto-applied — a human
    must review before activation.

    Only ALLOW/DENY overrides are learnable.  ASK_USER overrides are excluded.
    tool_args_short is truncated to 200 chars before storage.
    """
    try:
        return _log_override(
            tool_name=tool_name,
            tool_args_short=tool_args_short,
            classifier_decision=classifier_decision,
            user_override=user_override,
            session_id=session_id,
        )
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def config_migrate(source_path: str = "~/.claude/settings.json") -> Any:
    """Read Claude Code settings and emit an OpenCode-compatible migration block.
    
    Maps permission keys, flags unmappable keys for manual review,
    and filters secrets.  Source file is never modified.
    """
    try:
        return _config_migrate(source_path)
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def goal_loop(
    goal: str,
    max_turns: int = 10,
    cost_ceiling: float = 1.00,
    auto_mode: bool = False,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run a classifier-gated goal-oriented agent loop (simulation).

    Each turn: agent acts, classifier reviews, progress assessed.
    Terminates on: goal achieved, max_turns, cost exceeded, 3 consecutive DENY.

    Parameters
    ----------
    goal: Human-readable description of the task.
    max_turns: Max turns (≤ 50).  Default from config (10).
    cost_ceiling: Dollar ceiling for cumulative cost.  Default from config ($1.00).
    auto_mode: Reserved for future auto-approval.
    actions: List of simulated agent actions [{"tool_name": "...", ...}].

    Returns
    -------
    dict with keys: goal, status, turns_used, total_cost, wall_time_ms,
    output_summary, termination_reason, turns.
    """
    try:
        if max_turns > 50:
            return {"error": True, "message": "max_turns must be ≤ 50"}
        return _goal_loop(
            goal=goal,
            max_turns=max_turns,
            cost_ceiling=cost_ceiling,
            auto_mode=auto_mode,
            actions=actions,
        )
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def skill_load(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load and resolve a skill by name with argument substitution.

    Searches .agents/skills/, ~/.claude/skills/, .claude/skills/.
    Substitutes $0/$N/${NAME} placeholders. Returns resolved body,
    frontmatter, and warnings. Does NOT execute — text only.
    """
    arguments = arguments or {}
    try:
        return load_skill(name, arguments)
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def skill_list(filter_scope: str | None = None) -> Any:
    """List all available skills with name, description, path, and compatibility.

    Scans .agents/skills/, ~/.claude/skills/, and .claude/skills/
    directories. Cross-references with SKILL_COMPAT.md for
    compatibility status. Project skills take priority over user skills.

    Args:
        filter_scope: Optional filter ('verified', 'best_effort', 'unknown').
                      If omitted, returns all skills.
    """
    try:
        skills = _scan_skills()
        if filter_scope:
            skills = [s for s in skills if s["compatibility"] == filter_scope]
        return skills
    except Exception as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def session_cost_summary() -> dict[str, Any]:
    """Return accumulated per-session cost and token usage."""
    return _cost_tracker.summary()


@mcp.tool()
def count_tokens(text: str) -> dict[str, Any]:
    """Count tokens in text using tiktoken (cl100k_base encoding).

    Falls back to a rough character-count estimate if tiktoken is not installed.
    """
    token_count = _count_tokens(text)
    return {"tokens": token_count, "chars": len(text)}


if __name__ == "__main__":
    mcp.run()
