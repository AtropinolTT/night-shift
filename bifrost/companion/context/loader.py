"""AGENTS.md / CLAUDE.md discovery and loading for Bifrost companion.

Searches up the directory tree for AGENTS.md (preferred) or CLAUDE.md,
checks the user-level ``~/.config/opencode/AGENTS.md``, and resolves
``@import`` directives recursively (max 2 levels deep).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from bifrost.companion.config import load_config


# ── helpers ──────────────────────────────────────────────────────────────


def _token_count(text: str) -> int:
    """Approximate token count (1 token ≈ 4 characters)."""
    return len(text) // 4


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate *text* to fit within *max_tokens* (approx), cutting at the
    last newline before the character limit."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    cutoff = text[:max_chars]
    last_nl = cutoff.rfind("\n")
    if last_nl > 0:
        cutoff = cutoff[:last_nl]
    return cutoff


def _is_outside_project(path: Path, project_root: Path) -> bool:
    """Return ``True`` when *path* (after symlink resolution) does not
    reside under *project_root*."""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return True
    try:
        root_resolved = project_root.resolve()
    except (OSError, RuntimeError):
        return True
    return root_resolved not in resolved.parents and resolved != root_resolved


def _find_project_file(cwd: Path) -> Path | None:
    """Walk up from *cwd* returning the first ``AGENTS.md`` or ``CLAUDE.md``.

    ``CLAUDE.local.md`` is always skipped.  Symlinks pointing outside
    the containing directory are also skipped.
    Returns ``None`` when no candidate exists in the tree.
    """
    for parent in (cwd, *cwd.parents):
        for name in ("AGENTS.md", "CLAUDE.md"):
            candidate = parent / name
            if candidate.name.endswith(".local.md"):
                continue
            if candidate.exists() and not _is_outside_project(candidate, parent):
                return candidate
    return None


# ── @import resolution ────────────────────────────────────────────────────


_IMPORT_RE = re.compile(r"^\s*@(?!/)(.+)$", re.MULTILINE)


def _load_with_imports(
    file_path: Path,
    project_root: Path,
    depth: int = 0,
    max_depth: int = 2,
    seen: set[Path] | None = None,
) -> tuple[str, list[Path]]:
    """Load *file_path* and recursively resolve ``@import`` directives.

    Returns ``(content, sources)`` where *sources* lists every source
    file that contributed (deduplicated, in encounter order).
    """
    if seen is None:
        seen = set()

    resolved = file_path.resolve()
    if resolved in seen or depth > max_depth:
        return "", []

    seen.add(resolved)

    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "", []

    sources: list[Path] = [resolved]
    parts: list[str] = []
    cursor = 0

    for match in _IMPORT_RE.finditer(text):
        parts.append(text[cursor : match.start()])
        cursor = match.end()

        target = match.group(1).strip()
        imported = (resolved.parent / target).resolve()

        if _is_outside_project(imported, project_root):
            parts.append(f"<!-- @import {target}: skipped (outside project) -->\n")
            continue
        if not imported.exists():
            parts.append(f"<!-- @import {target}: not found -->\n")
            continue

        sub_content, sub_sources = _load_with_imports(
            imported, project_root, depth + 1, max_depth, seen
        )
        if sub_content:
            parts.append(sub_content + "\n")
            for s in sub_sources:
                if s not in sources:
                    sources.append(s)
        else:
            parts.append(text[match.start() : match.end()] + "\n")

    parts.append(text[cursor:])

    return "".join(parts), sources


# ── public API ────────────────────────────────────────────────────────────


def load_context(cwd: str | Path | None = None) -> dict:
    """Discover and load AGENTS.md / CLAUDE.md context.

    Parameters
    ----------
    cwd:
        Starting directory for the upward search.  Defaults to
        ``Path.cwd()``.

    Returns
    -------
    dict
        ``{"content": str, "sources": list[str], "truncated": bool}``.
        When no context file is found, *content* is an empty string and
        *sources* is an empty list.
    """
    cfg = load_config()
    max_tokens: int = cfg.max_context_tokens

    start = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()

    project_file = _find_project_file(start)
    project_root = project_file.parent if project_file else start

    user_file = Path.home() / ".config" / "opencode" / "AGENTS.md"

    all_parts: list[str] = []
    all_sources: list[Path] = []

    for fp in (project_file, user_file):
        if fp is None or not fp.exists():
            continue
        if fp.name.endswith(".local.md"):
            continue
        content, sources = _load_with_imports(fp, project_root)
        if content:
            all_parts.append(content)
            for s in sources:
                if s not in all_sources:
                    all_sources.append(s)

    combined = os.linesep.join(all_parts)
    total_tokens = _token_count(combined)
    truncated = total_tokens > max_tokens

    if truncated:
        combined = _truncate_to_tokens(combined, max_tokens)

    return {
        "content": combined,
        "sources": [str(p) for p in all_sources],
        "truncated": truncated,
    }
