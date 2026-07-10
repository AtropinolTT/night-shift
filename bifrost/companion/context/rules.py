"""Rule loading and path-scoped matching for .claude/rules/ files.

Scans the project's ``.claude/rules/`` directory for ``*.md`` files with
optional YAML frontmatter, parses ``paths:`` globs, and returns matched
rule content for context injection.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePath
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _find_rules_dir() -> Path | None:
    """Locate the nearest ``.claude/rules/`` by walking up from CWD."""
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / ".claude" / "rules"
        if candidate.is_dir():
            return candidate
    return None


def _parse_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Parse optional YAML frontmatter from rule content.

    Returns ``(frontmatter, body)``.  *frontmatter* is ``None`` when
    the frontmatter is malformed (caller should skip the rule); empty
    dict when there is no frontmatter block.  *body* is the remaining
    text (full *content* when the frontmatter is skipped).
    """
    lines = content.split("\n")
    if len(lines) >= 2 and lines[0].strip() == "---":
        end = 1
        while end < len(lines) and lines[end].strip() != "---":
            end += 1
        if end < len(lines):
            yaml_block = "\n".join(lines[1:end])
            body = "\n".join(lines[end + 1 :])
            try:
                frontmatter = yaml.safe_load(yaml_block) or {}
            except yaml.YAMLError:
                logger.warning("Skipping rule: malformed YAML frontmatter")
                return None, content
            if not isinstance(frontmatter, dict):
                return None, content
            return frontmatter, body
    return {}, content


def _expand_braces(pattern: str) -> list[str]:
    """Expand brace patterns (e.g. ``*.{tsx,jsx}``) into plain patterns.

    ``fnmatch`` / ``PurePath.match`` do not support brace expansion,
    so we flatten them client-side.  Handles one level of nesting.
    """
    if "{" not in pattern:
        return [pattern]
    results = [pattern]
    while any("{" in p for p in results):
        next_results: list[str] = []
        for p in results:
            if "{" not in p:
                next_results.append(p)
                continue
            start = p.index("{")
            depth = 1
            i = start + 1
            while i < len(p) and depth > 0:
                if p[i] == "{":
                    depth += 1
                elif p[i] == "}":
                    depth -= 1
                i += 1
            if depth != 0:
                next_results.append(p)
                continue
            end = i - 1
            prefix = p[:start]
            suffix = p[end + 1 :]
            for alt in p[start + 1 : end].split(","):
                next_results.append(prefix + alt + suffix)
        results = next_results
    return results


def _paths_match(file_path: str, patterns: list[str]) -> bool:
    """Check whether *file_path* matches any of the glob *patterns*."""
    fp = PurePath(file_path)
    for pattern in patterns:
        for expanded in _expand_braces(pattern):
            if fp.match(expanded):
                return True
    return False


def load_rules() -> list[dict[str, Any]]:
    """Load all rules from ``.claude/rules/`` without path filtering.

    Returns a list of dicts, each with keys:

    * **file** — relative path from the rules directory
    * **content** — full file content (including frontmatter)
    * **paths** — list of path glob patterns from the YAML ``paths:`` key
      (empty list when absent)

    Returns an empty list when ``.claude/rules/`` does not exist.
    """
    rules_dir = _find_rules_dir()
    if rules_dir is None:
        return []

    rules: list[dict[str, Any]] = []
    for fpath in sorted(rules_dir.glob("*.md")):
        try:
            text = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("Cannot read rule file %s, skipping", fpath.name)
            continue

        frontmatter, _ = _parse_frontmatter(text)
        if frontmatter is None:
            continue
        paths = frontmatter.get("paths", [])
        if not isinstance(paths, list):
            paths = []

        rules.append({
            "file": str(fpath.relative_to(rules_dir)),
            "content": text,
            "paths": paths,
        })

    return rules


def get_matching_rules(file_path: str) -> list[dict[str, Any]]:
    """Return rules whose path globs match *file_path*.

    Rules without a ``paths:`` key (or with an empty list) are
    considered global and always returned.

    Parameters
    ----------
    file_path:
        File path to match (e.g. ``"src/foo/bar.py"``).

    Returns
    -------
    list[dict]
        Matching rules with ``{file, content, paths}`` keys.

    Notes
    -----
    * Returns ``[]`` when ``.claude/rules/`` does not exist.
    * Malformed frontmatter skips the rule with a logged warning.
    * Symlinks outside the project directory are not followed.
    """
    rules = load_rules()
    return [
        rule
        for rule in rules
        if not rule["paths"] or _paths_match(file_path, rule["paths"])
    ]
