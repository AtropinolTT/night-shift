"""Claude Code → OpenCode settings migration.

Reads Claude Code settings (``~/.claude/settings.json``), maps each
permission key to its OpenCode equivalent, and returns the migration
as formatted text.  **Read-only** — the source file is never modified.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# ── secret detection patterns ────────────────────────────────────────────

def _is_secret(key: str, value: str) -> bool:
    """Check whether a key–value pair looks like a secret."""
    # Pattern 1: sk- prefix tokens (OpenAI / Anthropic style)
    if re.search(r"sk-[a-zA-Z0-9]{20,}", value):
        return True
    # Pattern 2: auth token key names
    if re.search(r"ANTHROPIC_AUTH_TOKEN", key, re.IGNORECASE):
        return True
    if re.search(r"OPENAI_API_KEY", key, re.IGNORECASE):
        return True
    # Pattern 3: generic api key / api-key patterns
    if re.search(r"api[_-]?key", key, re.IGNORECASE):
        return True
    # Pattern 4: values that are clearly tokens (long base64-like strings)
    # Tightened to require BOTH uppercase AND lowercase letters to avoid
    # false positives on "$5.00" (digits only), "AAAA..." (uppercase only),
    # "hello_world_..." (lowercase only), etc.
    if (
        len(value) >= 40
        and re.search(r"^[A-Za-z0-9+/=_-]+$", value)
        and re.search(r"[A-Z]", value)
        and re.search(r"[a-z]", value)
    ):
        return True
    # Pattern 5: JWT tokens (eyJ...)
    if re.search(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", value):
        return True
    # Pattern 6: AWS access keys (AKIA...)
    if re.search(r"AKIA[0-9A-Z]{16}", value):
        return True
    # Pattern 7: GitHub tokens (ghp_, github_pat_, gho_, ghu_, ghs_)
    if re.search(r"(?:ghp_|github_pat_|gho_|ghu_|ghs_)[A-Za-z0-9_]{36,}", value):
        return True
    # Pattern 8: Bearer tokens in config values (require 20+ chars after "Bearer "
    # to avoid false positives like "Bearer of bad news" or "Bearer my-token")
    if re.search(r"\bBearer\s+[A-Za-z0-9_\-\.]{20,}", value):
        return True
    # Pattern 9: Azure secrets (AccountKey, AZURE_CLIENT_SECRET, AZURE_STORAGE_KEY,
    # or SAS tokens starting with sv=)
    if re.search(
        r"(?:AccountKey|AccountName|AZURE_CLIENT_SECRET|AZURE_STORAGE_KEY|SAS_TOKEN|SharedAccessKey)",
        key,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"sv=[A-Za-z0-9\-]{10,}.*sig=[A-Za-z0-9+/=_\-]{20,}", value):
        return True
    # Pattern 10: PEM private keys (RSA, EC, OpenSSH, DSA)
    if re.search(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----",
        value,
    ):
        return True
    return False


# ── helpers ───────────────────────────────────────────────────────────────

def _filter_secrets(obj: Any, parent_key: str = "") -> Any:
    """Recursively walk *obj* and replace secret values with a marker."""
    if isinstance(obj, dict):
        return {
            k: _filter_secrets(v, parent_key=k)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_filter_secrets(v, parent_key=parent_key) for v in obj]
    if isinstance(obj, str) and _is_secret(parent_key, obj):
        return "// FILTERED"
    return obj


def _resolve_permissions(
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Handle both flat (``permissions.allow``) and nested
    (``permissions.allow``) permission formats, returning a dict
    with keys ``allow``, ``deny``, ``ask``."""
    result: dict[str, Any] = {}
    # Nested form: {"permissions": {"allow": [...], ...}}
    if "permissions" in settings and isinstance(settings["permissions"], dict):
        perms = settings["permissions"]
        for key in ("allow", "deny", "ask"):
            if key in perms:
                result[key] = perms[key]
    # Flat form: {"permissions.allow": [...], ...}
    for key in ("allow", "deny", "ask"):
        flat_key = f"permissions.{key}"
        if flat_key in settings and key not in result:
            result[key] = settings[flat_key]
    return result


def _format_value(val: Any, indent: int = 0) -> str:
    """Pretty-print a value as indented JSON with comment line style."""
    if val is None:
        return "// (none)"
    if isinstance(val, (dict, list)):
        return json.dumps(val, indent=2)
    if isinstance(val, bool):
        return "true" if val else "false"
    return json.dumps(val)


# ── per-key transforms ────────────────────────────────────────────────────

_CC_TO_OC_MODELS: dict[str, str] = {
    "sonnet": "deepseek-v4-flash",
    "opus": "deepseek-v4-pro",
    "haiku": "deepseek-v4-flash",
    "claude-sonnet-4-20250514": "deepseek-v4-flash",
    "claude-opus-4-20250514": "deepseek-v4-pro",
    "claude-3-5-sonnet-20241022": "deepseek-v4-flash",
}


def _transform_models(
    models: dict[str, str] | str | None,
) -> list[str]:
    """Map Claude Code model selection to OpenCode model config."""
    if models is None:
        return []

    lines: list[str] = ["// models → OpenCode equivalent"]
    if isinstance(models, str):
        oc_model = _CC_TO_OC_MODELS.get(models, models)
        lines.append(f'model: "{oc_model}"  // from Claude Code "{models}"')
    elif isinstance(models, dict):
        lines.append("models:")
        for k, v in models.items():
            if isinstance(v, str):
                oc_v = _CC_TO_OC_MODELS.get(v, v)
                lines.append(f'  {k}: "{oc_v}"  // from "{v}"')
            elif isinstance(v, bool):
                lines.append(f"  {k}: {'true' if v else 'false'}")
            else:
                lines.append(f"  {k}: {json.dumps(v)}")
    return lines


def _transform_allow_write(settings: dict[str, Any]) -> list[str]:
    """If ``allow_write_to_workspace`` is true, suggest adding Write
    to the allow list."""
    awtw = settings.get("allow_write_to_workspace")
    if awtw is None:
        return []
    lines = ["// allow_write_to_workspace → Write permission"]
    if awtw:
        lines.append('permissions.allow += ["Write"]  // workspace write enabled')
    else:
        lines.append("// allow_write_to_workspace: false — no change needed")
    return lines


def _transform_browser(settings: dict[str, Any]) -> list[str]:
    """Map Claude Code ``browser`` flag to OpenCode MCP server config."""
    browser = settings.get("browser")
    if browser is None:
        return []
    lines = ["// browser → mcp_servers.playwright"]
    if browser:
        lines.append("mcpServers.playwright:  // MANUAL REVIEW REQUIRED — verify MCP config")
        lines.append('  enabled: true')
    else:
        lines.append("// browser: false — playwright MCP not enabled")
    return lines


def _transform_bash(settings: dict[str, Any]) -> list[str]:
    """Map allowed bash commands to ``permissions.allow`` entries."""
    cmds = settings.get("allowedBashCommands")
    if not cmds or not isinstance(cmds, list):
        return []
    lines = ["// allowedBashCommands → permissions.allow (bash: prefix)"]
    bash_rules = [f"bash:{cmd}" for cmd in cmds if isinstance(cmd, str)]
    if bash_rules:
        lines.append(f"permissions.allow += {json.dumps(bash_rules)}")
    return lines


def _transform_verbose(settings: dict[str, Any]) -> list[str]:
    """Flag ``verbose`` as having no OpenCode equivalent."""
    verbose = settings.get("verbose")
    if verbose is None:
        return []
    lines = ["// MANUAL REVIEW REQUIRED: 'verbose' has no OpenCode equivalent"]
    lines.append(f"// Claude Code value: {json.dumps(verbose)}")
    lines.append("// Consider enabling debug logging in OpenCode settings instead")
    return lines


# ── public API ────────────────────────────────────────────────────────────


def config_migrate(source_path: str = "~/.claude/settings.json") -> str:
    """Read Claude Code settings and emit an OpenCode-compatible
    migration block.

    Parameters
    ----------
    source_path:
        Path to the Claude Code ``settings.json`` file.
        Defaults to ``~/.claude/settings.json`` (resolved with
        :func:`~pathlib.Path.expanduser`).

    Returns
    -------
    str
        Formatted migration block as text.  Sections that are
        directly mappable are included as ready-to-use config
        lines; unmappable keys are flagged with
        ``// MANUAL REVIEW REQUIRED``.  Secrets are replaced with
        ``// FILTERED``.
    """
    resolved = Path(source_path).expanduser()

    if not resolved.exists():
        return f"No Claude Code config found at {resolved}"

    try:
        raw = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading {resolved}: {exc}"

    try:
        settings: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        return f"Error parsing {resolved}: {exc}"

    # ── build output sections ─────────────────────────────────────────

    sections: list[str] = []
    header = [
        f"// {'=' * 60}",
        "// Migration from Claude Code settings",
        f"// Source: {resolved}",
        "// Copy relevant sections into your OpenCode config",
        f"// {'=' * 60}",
        "",
    ]
    sections.extend(header)

    # 1. 1:1 permission mappings
    perms = _resolve_permissions(settings)
    if perms:
        sections.append("// --- Permissions (1:1 mapped) ---")
        for key in ("allow", "deny", "ask"):
            if key in perms:
                clean = _filter_secrets(perms[key], parent_key=key)
                sections.append(f"permissions.{key}: {_format_value(clean)}")
        sections.append("")

    # 2. allow_write_to_workspace → Write
    awtw_lines = _transform_allow_write(settings)
    if awtw_lines:
        sections.extend(awtw_lines)
        sections.append("")

    # 3. models — handle both "model" (singular) and "models" (plural)
    model_val = settings.get("models") if "models" in settings else settings.get("model")
    model_lines = _transform_models(model_val)
    if model_lines:
        sections.extend(model_lines)
        sections.append("")

    # 4. browser → playwright
    browser_lines = _transform_browser(settings)
    if browser_lines:
        sections.extend(browser_lines)
        sections.append("")

    # 5. allowedBashCommands → bash: prefixed allow entries
    bash_lines = _transform_bash(settings)
    if bash_lines:
        sections.extend(bash_lines)
        sections.append("")

    # 6. verbose → MANUAL REVIEW
    verbose_lines = _transform_verbose(settings)
    if verbose_lines:
        sections.extend(verbose_lines)
        sections.append("")

    # 7. env — filter secrets, flag for review
    env = settings.get("env")
    if env and isinstance(env, dict):
        # Detect if any secrets were filtered
        filtered = _filter_secrets(env)
        has_secrets = filtered != env
        sections.append("// --- Environment variables ---")
        for k, v in sorted(filtered.items()):
            if isinstance(v, str) and v == "// FILTERED":
                sections.append(f"// {k}: FILTERED (secret removed)")
            else:
                sections.append(f"// {k}: {json.dumps(v)}")
        if has_secrets:
            sections.append(
                "// MANUAL REVIEW REQUIRED — secrets detected and filtered from env"
            )
        sections.append("")

    # 8. any remaining keys → MANUAL REVIEW
    known_keys = {
        "permissions.allow", "permissions.deny", "permissions.ask",
        "permissions",  # handled via _resolve_permissions
        "allow_write_to_workspace", "models", "model", "browser",
        "allowedBashCommands", "verbose", "env",
    }
    unknown = [k for k in settings if k not in known_keys]
    if unknown:
        sections.append("// --- MANUAL REVIEW REQUIRED ---")
        sections.append("// These keys have no direct OpenCode equivalent:")
        for key in sorted(unknown):
            clean_val = _filter_secrets(settings[key], parent_key=key)
            sections.append(f"//   {key}: {json.dumps(clean_val)}")
        sections.append("")

    return "\n".join(sections)


def config_migrate_project(project_root: str = ".") -> str:
    """Migrate project-level config files (e.g. ``.claude/settings.local.json``).

    Looks for known project-level config paths relative to *project_root*
    and returns a merged migration block.  Falls back gracefully when no
    project-level config is found.

    Parameters
    ----------
    project_root : str
        Root directory of the project (default: current directory).

    Returns
    -------
    str
        Formatted migration block, or an empty string if nothing was found.
    """
    root = Path(project_root).resolve()
    candidates: list[Path] = [
        root / ".claude" / "settings.local.json",
        root / ".claude" / "settings.json",
        root / ".opencode.json",
        root / ".opencode.jsonc",
    ]

    results: list[str] = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            result = config_migrate(str(candidate))
            if result and not result.startswith("No Claude Code config found"):
                results.append(
                    f"// Project-level config from: {candidate}\n{result}"
                )
        except Exception:
            continue

    return "\n\n".join(results) if results else ""
