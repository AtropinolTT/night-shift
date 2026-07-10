"""Bifrost companion configuration loader.

Reads config from XDG-compliant paths (~/.config/bifrost/config.yaml
or ~/.bifrost/config.yaml) with sensible defaults for all fields.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

# ── defaults ──────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "model_for_classifier": "deepseek-v4-flash",
    "model_for_fusion_synthesis": "deepseek-v4-pro",
    "max_context_tokens": 8000,
    "max_turns_default": 10,
    "cost_ceiling_default": 1.00,
    "allowlisted_bash_commands": [
        "ls",
        "cat",
        "git status",
        "git diff",
        "git log",
        "pwd",
        "echo",
        "python --version",
        "pip list",
    ],
}


# ── helpers ───────────────────────────────────────────────────────────────


def _config_path() -> Path:
    """Return the first existing config path per XDG Base Directory spec.

    Order of precedence:
    1. $XDG_CONFIG_HOME/bifrost/config.yaml
    2. ~/.bifrost/config.yaml
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        candidate = Path(xdg_config_home) / "bifrost" / "config.yaml"
        if candidate.exists():
            return candidate
    return Path.home() / ".bifrost" / "config.yaml"


def _validate(config: dict[str, Any]) -> None:
    """Validate loaded config values, raising ``ValueError`` on violations."""
    cmds = config.get("allowlisted_bash_commands", DEFAULTS["allowlisted_bash_commands"])
    if not isinstance(cmds, list) or not all(isinstance(c, str) for c in cmds):
        raise ValueError(
            "'allowlisted_bash_commands' must be a list of strings"
        )


def _merge(user_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Merge user-supplied config over defaults.

    Only keys present in *user_cfg* override the corresponding default.
    """
    merged = dict(DEFAULTS)
    if user_cfg:
        merged.update(user_cfg)
    return merged


# ── public API ────────────────────────────────────────────────────────────


def load_config(path: str | Path | None = None) -> SimpleNamespace:
    """Load Bifrost companion configuration.

    Reads YAML from *path* (or the default XDG-discovered location),
    merges over :data:`DEFAULTS`, validates, and returns a
    :class:`~types.SimpleNamespace` with attribute access.

    Parameters
    ----------
    path:
        Explicit config file path.  When *None* the XDG Base Directory
        spec is followed (see :func:`_config_path`).

    Returns
    -------
    SimpleNamespace
        Config object exposing every field as an attribute
        (e.g. ``cfg.max_context_tokens``).

    Raises
    ------
    FileNotFoundError
        Only when an explicit *path* is given and does not exist.
        Auto-discovered paths that are missing are silently ignored
        (defaults are used).
    yaml.YAMLError
        When the file exists but contains malformed YAML.  The error
        message includes the file path and offending line number.
    ValueError
        When a validated field fails its constraint.
    """
    resolved: Path | None = None

    if path is not None:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Config file not found: {resolved}")
    else:
        resolved = _config_path()

    user_cfg: dict[str, Any] | None = None

    if resolved is not None and resolved.exists():
        try:
            with open(resolved) as fh:
                user_cfg = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            if hasattr(exc, "problem_mark"):
                msg = (
                    f"Malformed YAML in {resolved}:{exc.problem_mark.line + 1} "
                    f"(column {exc.problem_mark.column + 1})"
                )
            else:
                msg = f"Malformed YAML in {resolved}: {exc}"
            raise yaml.YAMLError(msg) from exc

    merged = _merge(user_cfg)
    _validate(merged)
    return SimpleNamespace(**merged)
