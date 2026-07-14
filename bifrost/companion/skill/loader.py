"""Bifrost skill loader — argument substitution for skill bodies.

Parses SKILL.md files, substitutes ``$0``/``$N`` and ``${NAME}``
placeholders with provided arguments, and rejects shell exec
(``!`cmd```) patterns.

Anchor: bifrost-skill-loader
Phase: T7.2
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


# ── exceptions ─────────────────────────────────────────────────────────────


class ShellExecProhibited(ValueError):
    """Raised when a skill body contains inline shell execution (``!`cmd```)."""


class MissingArgument(KeyError):
    """Raised when a required argument placeholder has no provided value."""


# ── path resolution ───────────────────────────────────────────────────────

SKILL_SEARCH_PATHS: list[Path] = [
    # Project-level skills
    Path(".agents/skills"),
    # User-level skills
    Path.home() / ".claude" / "skills",
    # Repo-level skills (fallback)
    Path(".claude/skills"),
]

# ── regex constants ───────────────────────────────────────────────────────

_SHELL_EXEC_RE = re.compile(r"!`[^`]*`")
_ENV_VAR_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

# Sentinels for escaped dollar-sign round-trip
_ESC = "\x00ESC\x00"


# ── helpers ───────────────────────────────────────────────────────────────


def _find_skill_path(name: str) -> Path:
    """Find a *SKILL.md* file by skill name across search paths.

    Parameters
    ----------
    name : str
        Skill name — the directory name containing ``SKILL.md``.

    Returns
    -------
    Path
        Absolute or relative path to the discovered ``SKILL.md``.

    Raises
    ------
    FileNotFoundError
        No ``SKILL.md`` found in any search path.
    """
    searched: list[str] = []
    for base in SKILL_SEARCH_PATHS:
        candidate = base / name / "SKILL.md"
        searched.append(str(candidate))
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Skill '{name}' not found. Searched: "
        + ", ".join(searched)
    )


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split optional YAML frontmatter from the skill body.

    Parameters
    ----------
    content : str
        Raw ``SKILL.md`` file content.

    Returns
    -------
    tuple[dict, str]
        ``(frontmatter_dict, body_string)``.  If no frontmatter is
        present (or YAML is malformed) the dict will be empty.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    if not content.startswith("---\n"):
        return {}, content

    end = content.find("\n---\n", 4)
    if end == -1:
        # Empty frontmatter: "---\n---\nBody"
        end = content.find("\n---\n")
        if end == -1:
            return {}, content

    frontmatter_yaml = content[4:end]
    try:
        frontmatter = yaml.safe_load(frontmatter_yaml) or {}
    except yaml.YAMLError:
        frontmatter = {}

    body = content[end + 5:]  # skip the closing ``\n---\n``
    return frontmatter, body


# ── public API ────────────────────────────────────────────────────────────


def load_skill(
    name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and resolve a skill by name with argument substitution.

    Searches for ``SKILL.md`` in project, user, and repo-level skill
    directories, parses YAML frontmatter, detects prohibited shell exec
    patterns, and substitutes ``$0`` / ``$N`` / ``${NAME}`` placeholders
    with values from *arguments*.

    Parameters
    ----------
    name : str
        Skill name (directory name containing ``SKILL.md``).
    arguments : dict, optional
        Positional (``int`` / ``str`` keys) and named (``str`` keys)
        argument values.  Defaults to empty dict.

        * ``$0`` matches ``arguments[0]`` or ``arguments["0"]``.
        * ``$1``, ``$2``, ... match positional keys.
        * ``${NAME}`` matches ``arguments["NAME"]``.

    Returns
    -------
    dict
        Keys:

        * ``name`` — the skill name as passed in.
        * ``resolved_body`` — skill body with all placeholders replaced.
        * ``frontmatter`` — parsed YAML frontmatter as a dict (may be empty).
        * ``warnings`` — list of warning strings (env-var-like
          placeholders that were kept literal, etc.).

    Raises
    ------
    FileNotFoundError
        ``SKILL.md`` not found in any search path.
    ShellExecProhibited
        The skill body contains inline shell execution (``!`cmd```).
    MissingArgument
        A ``$N`` or ``${NAME}`` placeholder references an argument
        that was not provided in *arguments*.
    yaml.YAMLError
        Frontmatter is present but contains malformed YAML.
    """
    if arguments is None:
        arguments = {}

    # ── locate & read ──────────────────────────────────────────────────
    skill_path = _find_skill_path(name)
    raw = skill_path.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(raw)

    # ── security: detect shell exec ────────────────────────────────────
    if _SHELL_EXEC_RE.search(raw):
        raise ShellExecProhibited(
            f"Skill '{name}' contains inline shell execution (!`cmd`). "
            "Shell execution is prohibited in Bifrost skills."
        )

    # ── escape handling ────────────────────────────────────────────────
    # ``\$0`` → kept literal (round-trip via sentinel)
    body = body.replace(r"\$", _ESC)

    # ── shared argument lookup ─────────────────────────────────────────
    def _lookup(key: Any, *, label: str) -> str:
        """Return ``str(arguments[key])`` or raise ``MissingArgument``.

        Tries the key as-is first, then the stringified version.
        """
        if key in arguments:
            return str(arguments[key])
        str_key = str(key)
        if str_key in arguments:
            return str(arguments[str_key])
        raise MissingArgument(
            f"Missing argument for placeholder {label} in skill '{name}'"
        )

    warnings: list[str] = []

    # ── positional: $0, $1, $2, ... ────────────────────────────────────
    def _sub_positional(match: re.Match[str]) -> str:
        # Skip dollar amounts like $1, $0.01, $12/mo — only substitute
        # bare $N followed by whitespace, end-of-string, or punctuation
        # (not /, ., or another digit)
        nxt = match.end()
        if nxt < len(body) and body[nxt] not in (" ", "\t", "\n", "\r", ",", ";", ":", "!", "?", ")", "]", "}"):
            return match.group(0)
        idx = int(match.group(1))
        return _lookup(idx, label=f"${idx}")

    body = re.sub(r"\$(\d+)", _sub_positional, body)

    # ── named: ${NAME} ─────────────────────────────────────────────────
    def _sub_named(match: re.Match[str]) -> str:
        arg_name = match.group(1)
        if arg_name in arguments:
            return str(arguments[arg_name])
        # Environment variables are kept as-is
        if _ENV_VAR_RE.match(arg_name):
            msg = (
                f"Environment-like placeholder ${{{arg_name}}} "
                "kept literal (env vars are not substituted)"
            )
            if msg not in warnings:
                warnings.append(msg)
            return f"${{{arg_name}}}"
        raise MissingArgument(
            f"Missing argument for placeholder ${{{arg_name}}} in skill '{name}'"
        )

    body = re.sub(r"\$\{([A-Za-z_]\w*)\}", _sub_named, body)

    # ── restore escaped dollar signs ───────────────────────────────────
    body = body.replace(_ESC, "$")

    return {
        "name": name,
        "resolved_body": body,
        "frontmatter": frontmatter,
        "warnings": warnings,
    }
