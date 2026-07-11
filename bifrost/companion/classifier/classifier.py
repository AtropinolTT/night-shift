"""Tool-call security classifier with DEFAULT DENY policy.

Two-tier architecture:
1. **Pre-filter** (fast-path, ~0ms): instant decisions for known
   tool categories — read-only tools, allowlisted bash, write tools,
   destructive patterns.  Handles ~70% of calls without touching
   an LLM.
2. **Model dispatch** (slow-path, p95 ~1586ms on deepseek-v4-flash):
   cheap-model subagent reviews ambiguous tool calls.  Falls back
   to ASK_USER on timeout/error/parse-failure.

Expected caller: ``classify_tool_call(tool_name, tool_args, ...)``
returns a ``{"decision": ..., "reason": ...}`` dict.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from companion.classifier.feedback import check_active_learned_rules
from companion.config import load_config

# ═══════════════════════════════════════════════════════════════════════
#  Configuration  (loaded once at import time)
# ═══════════════════════════════════════════════════════════════════════

_cfg = load_config()
ALLOWLISTED_BASH: set[str] = set(_cfg.allowlisted_bash_commands)
MODEL_FOR_CLASSIFIER: str = _cfg.model_for_classifier
TIMEOUT_S: float = 5.0

# ═══════════════════════════════════════════════════════════════════════
#  Pre-filter: tool-name classification tables
# ═══════════════════════════════════════════════════════════════════════

# ── READ_ONLY_TOOLS — MUST KEEP IN SYNC with plugin/index.ts ──
# Tools that only *read* data — safe to ALLOW unconditionally.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Glob",
        "Grep",
        # LSP diagnostic / read operations
        "lsp_diagnostics",
        "lsp_find_references",
        "lsp_goto_definition",
        "lsp_symbols",
        "lsp_status",
        "lsp_prepare_rename",
    }
)

# Tools whose primary purpose is to *modify* the filesystem — always
# require human judgment.
WRITE_TOOLS: frozenset[str] = frozenset(
    {
        "Write",
        "Edit",
        "lsp_rename",  # applies workspace edits
    }
)

# Substrings that, when found in a *tool name*, trigger ASK_USER
# (catch-all for unknown write-like tools).
_WRITE_NAME_SUBSTRINGS: tuple[str, ...] = (
    "write",
    "edit",
    "create",
    "delete",
    "remove",
    "mkdir",
)

# Substrings that, when found in a *tool name*, trigger DENY
# (explicitly destructive tools).
_DESTRUCTIVE_NAME_SUBSTRINGS: tuple[str, ...] = (
    "rm",
    "chmod",
    "chown",
    "kill",
    "shutdown",
    "reboot",
    "format",
    "mount",
    "unmount",
    "dd",
    "mkfs",
    "fdisk",
    "parted",
)

# ═══════════════════════════════════════════════════════════════════════
#  Pre-filter: bash-command patterns
# ═══════════════════════════════════════════════════════════════════════

_DESTRUCTIVE_BASH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pat, re.IGNORECASE)
    for pat in (
        r"rm\s+.*-r(?:f|\s|$)",               # rm -rf, rm -r (short flag)
        r"rm\s+.*-f(?:r|\s|$)",               # rm -fr, rm -f
        r"rm\s+--recursive",                   # rm --recursive
        r"chmod\s+777",
        r"chmod\s+o\+w",
        r"curl.*\|\s*(?:ba)?sh",            # curl | sh
        r"wget.*\|\s*(?:ba)?sh",            # wget | sh
        r">\s*/dev/sd[a-z]",                # overwrite block device
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r"shutdown\b",
        r"reboot\b",
        r"halt\b",
        r"poweroff\b",
        r":\(\)\s*\{",                      # fork bomb
    )
]

# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _bash_allowlisted(command: str) -> bool:
    """True when *command* starts with an allowlisted prefix."""
    stripped = command.lstrip()
    for allowed in sorted(ALLOWLISTED_BASH, key=len, reverse=True):
        if stripped.startswith(allowed):
            # Also check that the next char (if any) is a separator
            # so "grep" doesn't match "grepfoo".
            remainder = stripped[len(allowed) :]
            if not remainder or remainder[0] in (" ", ";", "|", "&", "\n", "\0"):
                return True
    return False


def _bash_destructive(command: str) -> bool:
    """True when *command* matches a known destructive pattern."""
    return any(p.search(command) for p in _DESTRUCTIVE_BASH_PATTERNS)


# ═══════════════════════════════════════════════════════════════════════
#  Prompt builder  (no secrets exposed)
# ═══════════════════════════════════════════════════════════════════════

_SECURITY_SYSTEM = (
    "You are a strict security classifier for agent tool calls. "
    "Your ONLY job is to respond with EXACTLY one decision word "
    "(ALLOW, DENY, or ASK_USER) followed by a colon and a one-line reason. "
    "Never explain further. Never include extra text.\n\n"
    "- ALLOW: the operation reads data without side effects.\n"
    "- DENY: the operation is destructive, dangerous, or bypasses security.\n"
    "- ASK_USER: the operation modifies state and needs human judgment.\n\n"
    "Respond in format: DECISION: reason"
)


def _build_prompt(
    tool_name: str,
    tool_args: dict[str, Any],
    file_paths: list[str] | None,
    session_context: dict[str, Any] | None,
) -> str:
    """Build the security-review prompt — **no secrets exposed**."""
    # Sanitize tool_name — prevent prompt injection via newlines, control chars,
    # Unicode homoglyphs, decision keywords, or excessive length.
    if not isinstance(tool_name, str):
        raise ValueError(f"Tool name must be a string, got {type(tool_name).__name__}")
    if len(tool_name) > 128:
        raise ValueError(f"Tool name too long ({len(tool_name)} > 128 chars): {tool_name!r}")
    if "\n" in tool_name or "\r" in tool_name or "\t" in tool_name:
        raise ValueError(
            f"Tool name contains whitespace/control chars (possible injection): {tool_name!r}"
        )
    if not all(ord(c) >= 32 and ord(c) < 0x110000 for c in tool_name):
        raise ValueError(
            f"Tool name contains invalid Unicode characters: {tool_name!r}"
        )
    # Reject decision keywords embedded in the tool name (case-insensitive)
    # to prevent "my_ALLOW_tool" or "readDENY" from biasing the model.
    lowered = tool_name.lower()
    for keyword in ("allow", "deny", "ask_user"):
        if keyword in lowered:
            raise ValueError(
                f"Tool name contains decision keyword {keyword!r} (possible prompt injection): {tool_name!r}"
            )
    # Normalize Unicode homoglyphs (fullwidth Latin → ASCII) to prevent
    # Ｒｅａｄ looking identical to "Read" to humans but different to the model.
    import unicodedata
    tool_name = unicodedata.normalize("NFKC", tool_name)
    tool_name_display = tool_name.replace(":", "\\:")

    context_parts: list[str] = [
        f"Tool: {tool_name_display}",
    ]

    # Truncate args to avoid prompt bloat / accidental secret leak
    args_str = json.dumps(tool_args, default=str)
    if len(args_str) > 2000:
        args_str = args_str[:1997] + "..."
    context_parts.append(f"Arguments: {args_str}")

    if file_paths:
        fp = json.dumps(file_paths[:20])  # cap at 20 paths
        context_parts.append(f"Files: {fp}")

    if session_context:
        # Only include safe keys — never raw tokens or env
        safe_keys = {"goal", "task_id", "project", "cwd", "tool_count"}
        safe_ctx = {k: session_context[k] for k in safe_keys if k in session_context}
        if safe_ctx:
            context_parts.append(f"Session: {json.dumps(safe_ctx, default=str)}")

    return "\n".join(context_parts)


# ═══════════════════════════════════════════════════════════════════════
#  Model dispatch  (slow-path)
# ═══════════════════════════════════════════════════════════════════════


def _parse_response(content: str) -> dict[str, str]:
    """Extract decision + reason from model output.

    Accepts ``ALLOW: reason``, ``DENY: reason``, ``ASK_USER: reason``,
    or just a bare word.  Falls back to ASK_USER on parse failure.
    """
    text = content.strip()

    # Exact format: "DECISION: reason" or "DECISION reason"
    m = re.match(
        r"^\s*(ALLOW|DENY|ASK_USER)\s*[:]\s*(.*)",
        text,
        re.IGNORECASE,
    )
    if m:
        decision = m.group(1).upper()
        reason = m.group(2).strip() or "indeterminate"
        return {"decision": decision, "reason": reason}

    # Loose match: just find the decision word somewhere
    for candidate in ("ALLOW", "DENY", "ASK_USER"):
        if re.search(rf"\b{candidate}\b", text, re.IGNORECASE):
            return {
                "decision": candidate,
                "reason": f"model: {text[:120]}",
            }

    return {
        "decision": "ASK_USER",
        "reason": f"unparseable model response: {text[:120]}",
    }


def _dispatch_sync(prompt: str) -> dict[str, str]:
    """Send *prompt* to the cheap classifier model (sync, with timeout).

    Returns ``{"decision": ..., "reason": ...}`` — always ASK_USER on
    any failure.
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return {
            "decision": "ASK_USER",
            "reason": "no DEEPSEEK_API_KEY configured",
        }

    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            resp = client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL_FOR_CLASSIFIER,
                    "messages": [
                        {"role": "system", "content": _SECURITY_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 80,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            content: str = body["choices"][0]["message"]["content"]
            return _parse_response(content)

    except (httpx.TimeoutException, httpx.HTTPError, httpx.InvalidURL):
        return {
            "decision": "ASK_USER",
            "reason": "classifier model timeout or network error",
        }
    except (KeyError, IndexError, TypeError):
        return {
            "decision": "ASK_USER",
            "reason": "classifier model returned unexpected format",
        }
    except Exception:
        return {
            "decision": "ASK_USER",
            "reason": "classifier model unexpected error",
        }


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════


def classify_tool_call(
    tool_name: str,
    tool_args: dict[str, Any],
    file_paths: list[str] | None = None,
    session_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Classify a tool call with DEFAULT DENY policy.

    **Fast-path** (no model call, ~0 ms):
      - Read-only tools → ``ALLOW``
      - Allowlisted bash commands → ``ALLOW``
      - Write / edit / create / delete / remove / mkdir tools → ``ASK_USER``
      - Destructive tools → ``DENY``

    **Slow-path** (cheap-model dispatch, ~1-2 s):
      - Everything else goes through a security-review prompt.
      - Falls back to ``ASK_USER`` on timeout, network error,
        or unparseable response.

    Parameters
    ----------
    tool_name:
        Name of the tool being called (e.g. ``"Bash"``, ``"Write"``).
    tool_args:
        Tool arguments dict.  For Bash this must contain ``"command"``.
    file_paths:
        Optional list of file paths the tool will touch.
    session_context:
        Optional session metadata (goal, project, …).

    Returns
    -------
    dict
        ``{"decision": "ALLOW"|"DENY"|"ASK_USER", "reason": "…"}``
    """
    # ── 1. Read-only tools → ALLOW (instant) ──────────────────────
    if tool_name in READ_ONLY_TOOLS:
        return {"decision": "ALLOW", "reason": f"read-only: {tool_name}"}

    # ── 2. Bash tool — multi-stage check ──────────────────────────
    if tool_name in ("Bash", "bash", "interactive_bash"):
        command: str = str(tool_args.get("command", ""))
        if not command:
            return {"decision": "DENY", "reason": "bash called with empty command"}

        # Destructive patterns → DENY
        if _bash_destructive(command):
            return {"decision": "DENY", "reason": "destructive bash command detected"}

        # Allowlisted commands → ALLOW
        if _bash_allowlisted(command):
            return {"decision": "ALLOW", "reason": f"allowlisted: {command[:80]}"}

        # Check active learned rules before model dispatch
        learned = check_active_learned_rules(tool_name, tool_args)
        if learned is not None:
            return {
                "decision": learned["decision"],
                "reason": f"learned rule #{learned['rule_id']}: {learned['decision']}",
            }

        # Unknown bash → model dispatch
        prompt = _build_prompt(tool_name, tool_args, file_paths, session_context)
        return _dispatch_sync(prompt)

    # ── 3. Write tools → ASK_USER ─────────────────────────────────
    if tool_name in WRITE_TOOLS:
        return {
            "decision": "ASK_USER",
            "reason": f"write tool: {tool_name}",
        }

    # ── 4. Write-like tool name → ASK_USER ────────────────────────
    tl = tool_name.lower()
    if any(ws in tl for ws in _WRITE_NAME_SUBSTRINGS):
        return {
            "decision": "ASK_USER",
            "reason": f"write-related tool: {tool_name}",
        }

    # ── 5. Destructive tool name → DENY ───────────────────────────
    if any(ds in tl for ds in _DESTRUCTIVE_NAME_SUBSTRINGS):
        return {
            "decision": "DENY",
            "reason": f"destructive tool: {tool_name}",
        }

    # ── 6. Check active learned rules before model dispatch ───────
    learned = check_active_learned_rules(tool_name, tool_args)
    if learned is not None:
        return {
            "decision": learned["decision"],
            "reason": f"learned rule #{learned['rule_id']}: {learned['decision']}",
        }

    # ── 7. Unknown → model dispatch (slow-path) ───────────────────
    prompt = _build_prompt(tool_name, tool_args, file_paths, session_context)
    return _dispatch_sync(prompt)
