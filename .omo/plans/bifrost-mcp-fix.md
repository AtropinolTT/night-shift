# Bifrost MCP Companion — Fix Plan

**Author**: Sisyphus-Junior  
**Date**: 2026-07-13  
**Status**: Draft — awaiting approval  

---

## TL;DR for Humans

Bifrost has 5 bugs. Here's what they are and how to fix them:

1. **Dual companion processes**: OpenCode's `opencode.json` MCP config spawns one Python companion. The plugin (`mcp-relay.ts`) spawns another. Two processes, no shared state, double the memory. **Fix**: Remove the MCP config from `opencode.json` — the plugin is the sole companion lifecycle manager.

2. **NFS bytecode cache staleness**: Python's `__pycache__` compares `.py` vs `.pyc` timestamps. NFS timestamps don't update reliably. Python uses stale bytecode after source edits. **Fix**: Set `PYTHONDONTWRITEBYTECODE=1` and add `importlib.invalidate_caches()` + delete `__pycache__` at startup.

3. **chat.message hook reads from wrong field**: Already fixed (reads `output.parts` now). **Status**: ✅ Done, just verify.

4. **Classifier blocks innocent bash commands**: Commands not on the allowlist (only 8 entries) go through slow model dispatch which may return `DENY`. **Fix**: Default unknown bash commands to `ALLOW` (destructive patterns still block).

5. **Remove fusion from companion**: Fusion dispatch is now handled by the plugin's `task()` directly. The companion's `fusion_dispatch_tool`, `configure`, and `_call_via_openode` are dead code. **Fix**: Strip all fusion code from companion, keep the plugin's SDK-based dispatch.

---

## Scope

### IN
- Consolidate to single companion process (plugin-managed)
- Fix NFS bytecode cache staleness
- Fix classifier blocking innocent bash commands
- Remove fusion dispatch from companion (`server.py`, `dispatch.py`)
- Remove `configure` MCP tool from companion
- Clean up `/explain` slash command to use SDK dispatch instead of companion
- Ensure ALL other MCP tools work correctly (memory, classifier, goal, skill, audit)

### OUT
- No fusion-related changes in the plugin (fusion already uses `sdkFusionDispatch`)
- No changes to the fusion skill file
- No OpenCode core modifications

---

## Root Cause Analysis

### Bug 1: Dual Companion Processes

**Root cause**: Two independent spawn points for the same Python process.

**Spawn point A** — `~/.config/opencode/opencode.json`:
```jsonc
"mcp": {
  "bifrost-companion": {
    "type": "local",
    "command": ["python3", "/sibcb1/.../bifrost/companion/server.py"],
    "enabled": true
  }
}
```
This makes the companion's MCP tools (`memory_save`, `classify_tool_call`, `goal_loop`, `fusion_dispatch_tool`, `skill_load`, etc.) available to the agent as first-class callable tools. OpenCode spawns this process as a child and communicates via stdio JSON-RPC.

**Spawn point B** — `bifrost/plugin/index.ts` line 607:
```typescript
await relay.connect(undefined, COMPANION_SCRIPT);
```
Then line 610:
```typescript
await relay.call("configure", { server_url: pluginInput.serverUrl.toString() });
```
The plugin spawns its OWN companion process (via `MCPRelay` — `spawn(python3, [script])`). This is used programmatically from hooks — the classifier is called via `monitor.call("classify_tool_call", ...)` in `tool.execute.before`.

**Why it's a problem**:
1. **No shared state**: `_openode_server_url` is set on the plugin's companion via `configure`, but the MCP companion (spawn point A) never receives this. If the agent calls `fusion_dispatch_tool` through MCP, it won't have the server URL. (Mitigated by the fact that fusion uses `opencode run` subprocess, which doesn't need the URL for dispatch — but the URL IS needed for `_call_via_openode` in the original code path.)
2. **Duplicate resource usage**: Two Python processes, two SQLite connections, two in-memory caches.
3. **Config drift**: The classifier caches config at import time. Restart one, the other has stale config.
4. **Confusion about which companion handles which request**: Plugin calls go to spawn-B; agent MCP calls go to spawn-A.

**Solution**: Remove spawn point A (the `opencode.json` MCP config entry). The plugin already manages the companion lifecycle with health monitoring, circuit breaker, and graceful restart. The agent doesn't need bifrost's tools as first-class MCP tools — it already uses them through slash commands (`/goal`, `/review`, `/commit`, `/test`, `/audit-permissions`) and the plugin's automatic hooks (classifier, compacting memory save, error memory save).

However, there's a risk: if the agent needs to call `memory_save` or `skill_load` directly (not through a slash command), it can't without the MCP config. Assessment:
- The agent already calls `memory_save` directly? No — the plugin auto-saves memory on `session.compacting` and `tool.execute.after` errors. The agent doesn't manually trigger memory save.
- `skill_load` is only called through `/review`, `/commit`, `/test` slash commands.
- `classify_tool_call` is only called from `tool.execute.before` — not by the agent directly.
- `classify_tool_call` is currently only called from `tool.execute.before` — not by the agent.

**Conclusion**: Safe to remove the MCP config. The plugin is the sole companion manager.

---

### Bug 2: NFS Bytecode Cache Staleness

**Root cause**: Python's `__pycache__` mechanism compares `.py` source mtime to `.pyc` mtime. On NFS (`10.42.1.25:/chuyanyilab1`), file modification timestamps may not update atomically or synchronously across clients.

**Concrete scenario**:
1. Companion starts, imports modules → `__pycache__` created with timestamp T1.
2. Developer edits `classifier.py`.
3. Companion restarted (or receives new request). Python checks `classifier.py` mtime (T1 on NFS — stale) vs `classifier.pyc` mtime (T1). They match → Python loads stale bytecode.
4. Bug persists until `__pycache__` is manually deleted.

**Solution**: Three-pronged defense:

1. **Environment variable**: Set `PYTHONDONTWRITEBYTECODE=1` in the companion's spawn environment. This prevents Python from writing `.pyc` files entirely, forcing recompilation from source on every import.

2. **Startup cleanup**: In `server.py`, before imports, delete `__pycache__` directories recursively. This handles the case where stale `.pyc` files already exist from previous runs (before the env var was set).

3. **`importlib.invalidate_caches()`**: Call at the top of `server.py` after imports to clear Python's internal finder cache.

**Files affected**:
- `bifrost/plugin/mcp-relay.ts` line 329: Add `PYTHONDONTWRITEBYTECODE: "1"` to the env object
- `bifrost/companion/server.py`: Add `__pycache__` cleanup + `importlib.invalidate_caches()` before imports

---

### Bug 3: chat.message Hook Reads Wrong Field

**Root cause**: The original code on line ~1078 read `(input as any)?.message?.parts?.[0]?.text` — but the `input` object of a `chat.message` hook has no `.message` property. The user message content is in `output.parts`.

**Current status**: This bug is **already fixed** in the current codebase (line 1083):
```typescript
const text = (output.parts?.find(p => p.type === "text") as any)?.text ?? "";
```
**Verification needed**: Confirm this line correctly reads the user's slash command text from `output.parts`.

**No action required** — but should be listed in the plan as verified.

---

### Bug 4: Classifier Blocks Innocent Bash Commands

**Root cause**: The classifier has a default-deny posture for unknown bash commands. The flow:

1. Plugin's `tool.execute.before` fires for `Bash`.
2. `Bash` is NOT in `READ_ONLY_TOOLS` → sent to classifier.
3. Classifier checks: `command` is not empty → proceed; not destructive → proceed; not allowlisted → **model dispatch**.
4. Model dispatch sends the command to `deepseek-v4-flash` for classification.
5. Model may return `DENY` for commands it doesn't recognize (e.g., `npm install`, `cargo build`, `python script.py`).
6. Result: Innocent commands are blocked.

The default allowlist (`config.py` line 26-35) is only 8 entries:
```python
"allowlisted_bash_commands": [
    "ls", "git status", "git diff", "git log",
    "pwd", "echo", "python --version", "pip list",
]
```

Most agent bash commands (`grep`, `find`, `npm`, `cargo`, `python`, `node`, `mkdir`, `cp`, `mv`, `cat`, `curl`, `wget`, `gh`, `docker`, `systemctl`, etc.) are NOT in the allowlist.

**Solution**: In the classifier (`classifier.py`), change the Bash section default from model dispatch to **ALLOW**. The destructive pattern check and allowlist check still run first. Unknown commands default to ALLOW instead of going to model dispatch.

**Rationale**:
1. The destructive pattern check already catches truly dangerous commands (`rm -rf`, `chmod 777`, fork bombs, etc.).
2. The model dispatch adds latency (~1.5s) and can produce false `DENY` for common dev commands.
3. The agent should be trusted to run arbitrary bash commands — bifrost is a safety net, not a cage.
4. If stricter bash control is needed, the user can expand `allowlisted_bash_commands` in config.yaml (which runs before the default-allow path).

**Alternative considered**: Adding `Bash` to `READ_ONLY_TOOLS` in the plugin would bypass ALL classification (including destructive checks). Rejected — too permissive.

---

### Bug 5: Remove Fusion from Companion

**Root cause**: Fusion dispatch was originally implemented in the companion. The plugin has since been upgraded to use `sdkFusionDispatch()` which calls OpenCode's SDK directly (`client.session.create` + `client.session.prompt`). The companion's fusion code is dead code.

**Additionally**: The import `from companion.fusion.dispatch import fusion_dispatch, set_server_url` on line 24 of `server.py` references `set_server_url` which **does not exist** in `dispatch.py`. This would cause an `ImportError` at companion startup — the companion may be silently failing to start since this bug was introduced.

**What to remove**:

| File | Removals |
|------|----------|
| `companion/server.py` | `fusion_dispatch_tool` tool (lines 186-210), `fusion_dispatch` import (line 24), `set_server_url` import (line 24), `configure` tool (lines 125-131), `_openode_server_url` global (line 42) |
| `companion/fusion/dispatch.py` | Entire file can be deleted, OR keep as reference but strip all code. Actually, DELETE the entire file and the `companion/fusion/` directory. |
| `companion/config.py` | Remove `model_for_fusion_synthesis`, `fusion_models`, `fusion_synthesis_model` from `DEFAULTS` (lines 20-22). Keep all other defaults. |
| `plugin/index.ts` | `/explain` command (lines 899-945) currently calls `fusion_dispatch_tool` via relay. This needs to be rewritten to use `sdkFusionDispatch()` instead (the plugin already has this function at lines 322-499). |

**The `/explain` command**: Currently calls `fusion_dispatch_tool` through the companion relay with a single model (deepseek-v4-pro). After companion fusion removal, it must use `sdkFusionDispatch()` directly. This is a fall-forward: the SDK dispatch is already the primary path for `/fusion`. `/explain` was missed during the previous migration.

---

## Task Breakdown

### Wave 1: Independent, Low-Risk (parallelizable)

#### Task 1.1: Fix NFS bytecode cache staleness
**Priority**: High | **Dependencies**: None

**Files**:
- `bifrost/plugin/mcp-relay.ts` line 329
- `bifrost/companion/server.py` lines 1-17

**Changes — `mcp-relay.ts`** (line 329):
```typescript
// BEFORE:
env: { ...process.env, PYTHONUNBUFFERED: "1" },
// AFTER:
env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONDONTWRITEBYTECODE: "1" },
```

**Changes — `server.py`** (after line 17, before imports):
```python
# ── NFS bytecode cache staleness mitigation ─────────────────────────────
# NFS may serve stale timestamps, causing Python to reuse outdated .pyc
# files even after source changes. Two defenses:
# 1. PYTHONDONTWRITEBYTECODE=1 (set in mcp-relay.ts env) prevents new .pyc
# 2. Delete existing __pycache__ at startup + invalidate finder caches
import importlib
import shutil
_SELF_DIR = Path(__file__).resolve().parent
for pycache in _SELF_DIR.parent.rglob("__pycache__"):
    try:
        shutil.rmtree(pycache)
    except OSError:
        pass
_SELF_DIR = Path(__file__).resolve().parent  # re-assign after cleanup
importlib.invalidate_caches()
```

Note: `_SELF_DIR` is already defined at line 15. Move the `sys.path` fix BEFORE the cache cleanup, then add cleanup after it, then do imports. Reorder:
1. `_SELF_DIR` + `sys.path` fix (lines 15-17)
2. `importlib.invalidate_caches()` (immediate, before any companion imports)
3. `__pycache__` cleanup (delete existing stale bytecode)
4. Then all companion imports (lines 20-34)

**Acceptance Criteria**:
- Companion starts without error
- No `__pycache__` directories exist under `bifrost/companion/` after startup
- `echo $PYTHONDONTWRITEBYTECODE` in the companion process shows `1`

**QA**:
1. Start companion → verify startup logs are clean
2. Check `ls bifrost/companion/fusion/__pycache__` → should not exist
3. Make a trivial edit to `classifier.py`, restart companion → change takes effect (manual verification)

---

#### Task 1.2: Fix classifier blocking Bash commands
**Priority**: High | **Dependencies**: None

**File**: `bifrost/companion/classifier/classifier.py` lines 356-379

**Changes**: In the Bash section, change the default from model dispatch to ALLOW:

```python
# BEFORE (lines 356-379):
if tool_name in ("Bash", "bash", "interactive_bash"):
    command: str = str(tool_args.get("command", ""))
    if not command:
        return {"decision": "DENY", "reason": "bash called with empty command"}
    if _bash_destructive(command):
        return {"decision": "DENY", "reason": "destructive bash command detected"}
    if _bash_allowlisted(command):
        return {"decision": "ALLOW", "reason": f"allowlisted: {command[:80]}"}
    learned = check_active_learned_rules(tool_name, tool_args)
    if learned is not None:
        return { ... }
    # Unknown bash → model dispatch
    prompt = _build_prompt(tool_name, tool_args, file_paths, session_context)
    return _dispatch_sync(prompt)

# AFTER:
if tool_name in ("Bash", "bash", "interactive_bash"):
    command: str = str(tool_args.get("command", ""))
    if not command:
        return {"decision": "DENY", "reason": "bash called with empty command"}
    if _bash_destructive(command):
        return {"decision": "DENY", "reason": "destructive bash command detected"}
    if _bash_allowlisted(command):
        return {"decision": "ALLOW", "reason": f"allowlisted: {command[:80]}"}
    # Learned rules: apply if active (human reviewed)
    learned = check_active_learned_rules(tool_name, tool_args)
    if learned is not None:
        return {
            "decision": learned["decision"],
            "reason": f"learned rule #{learned['rule_id']}: {learned['decision']}",
        }
    # Default: ALLOW. The destructive pattern check already catches
    # dangerous commands. Model dispatch for bash is unreliable (often
    # returns DENY for innocent dev commands like `npm install`).
    return {"decision": "ALLOW", "reason": f"bash command: {command[:80]}"}
```

**Acceptance Criteria**:
- `Bash` with `command: "npm install express"` returns `ALLOW`
- `Bash` with `command: "rm -rf /"` returns `DENY`
- `Bash` with `command: "ls"` returns `ALLOW` (fast path)
- No model dispatch for ANY bash command

**QA**:
1. Call `classify_tool_call("Bash", {"command": "cargo build"})` → `{"decision": "ALLOW", ...}`
2. Call `classify_tool_call("Bash", {"command": "rm -rf /tmp/*"})` → `{"decision": "DENY", ...}`
3. Call `classify_tool_call("Bash", {"command": "git status"})` → `{"decision": "ALLOW", ...}` (allowlisted fast path)
4. Verify response time is <1ms (no model dispatch)

---

### Wave 2: Fusion Removal from Companion (sequential within this wave, all depend on each other)

#### Task 2.1: Remove `configure` MCP tool and `_openode_server_url` global
**Priority**: High | **Dependencies**: None (can run parallel to Wave 1)

**File**: `bifrost/companion/server.py` lines 24, 41-42, 125-131

**Changes**:
1. Remove `from companion.fusion.dispatch import fusion_dispatch, set_server_url` (line 24)
2. Remove `_openode_server_url: str | None = None` (lines 41-42)
3. Remove the entire `configure` tool function (lines 125-131)

**After removal**, server.py imports should look like:
```python
from companion.classifier.classifier import classify_tool_call as _classify_tool_call
from companion.classifier.feedback import log_override as _log_override
from companion.cost.tracker import SessionCostTracker
# fusion import line REMOVED
from companion.goal.loop import goal_loop as _goal_loop
from companion.memory.list import list_memories
from companion.memory.store import save_memory, delete_memory
from companion.memory.context import search_memory
from companion.permission.migrate import config_migrate as _config_migrate
from companion.skill.loader import _parse_frontmatter, load_skill
from companion.utils.tokenizer import count_tokens as _count_tokens
```

And after the `_cost_tracker` line, remove the `_openode_server_url` block.

**Acceptance Criteria**:
- `from companion.fusion.dispatch` no longer imported in server.py
- No reference to `configure`, `_openode_server_url`, or `set_server_url` in server.py
- Companion starts without ImportError

**QA**:
1. Start companion: `python3 server.py` (should start clean, no import errors)
2. Call any other tool (e.g., `echo`, `version`) via MCP → works

---

#### Task 2.2: Remove `fusion_dispatch_tool` MCP tool from server.py
**Priority**: High | **Dependencies**: Task 2.1

**File**: `bifrost/companion/server.py` lines 186-210

**Changes**: Delete the entire `fusion_dispatch_tool` function decorated with `@mcp.tool()`.

**Acceptance Criteria**:
- No `fusion_dispatch_tool` tool registered in the companion's MCP server
- `fusion` keyword does not appear in server.py (except maybe in config defaults, which are handled separately)
- Existing non-fusion tools (memory, classifier, goal, skill, audit) still work

**QA**:
1. Start companion
2. List tools via MCP `tools/list` → `fusion_dispatch_tool` should NOT appear
3. Verify `memory_save`, `classify_tool_call`, `goal_loop`, `skill_load` still appear

---

#### Task 2.3: Delete companion/fusion/ directory and dispatch.py
**Priority**: High | **Dependencies**: Tasks 2.1, 2.2

**File**: `bifrost/companion/fusion/dispatch.py` (entire file, 585 lines)
**Directory**: `bifrost/companion/fusion/` (entire directory, including `__init__.py` and `__pycache__/`)

**Changes**: 
```bash
rm -rf bifrost/companion/fusion/
```

**Acceptance Criteria**:
- `bifrost/companion/fusion/` directory no longer exists
- No import errors in any remaining companion code
- Git diff shows deletion of all fusion files

**QA**:
1. `ls bifrost/companion/fusion/` → "No such file or directory"
2. `python3 companion/server.py` → starts clean

---

#### Task 2.4: Remove fusion-related config defaults
**Priority**: Medium | **Dependencies**: Task 2.3

**File**: `bifrost/companion/config.py` lines 20-22

**Changes**: Remove from `DEFAULTS`:
```python
# REMOVE these three lines:
"model_for_fusion_synthesis": "deepseek-v4-pro",
"fusion_models": ["deepseek-v4-pro", "deepseek-v4-flash"],
"fusion_synthesis_model": "deepseek-v4-pro",
```

Keep `model_for_classifier` (still needed by classifier).

**Acceptance Criteria**:
- `config.py` DEFAULTS has no fusion-related keys
- Loading config without a config.yaml file doesn't reference fusion fields
- Classifier still gets `model_for_classifier` from DEFAULTS

**QA**:
1. `python3 -c "from companion.config import load_config; c = load_config(); print(c.model_for_classifier)"` → outputs `deepseek-v4-flash`
2. `python3 -c "from companion.config import load_config; c = load_config(); print(hasattr(c, 'fusion_models'))"` → `False`

---

#### Task 2.5: Rewrite `/explain` slash command to use SDK dispatch
**Priority**: High | **Dependencies**: Tasks 2.1, 2.2 (can't use relay for fusion after those)

**File**: `bifrost/plugin/index.ts` lines 899-945

**Changes**: Replace the `/explain` command block that calls `fusion_dispatch_tool` through relay with a direct `sdkFusionDispatch` call:

```typescript
// ── /explain ──────────────────────────────────────────────────
if (input.command === "explain") {
  const rawArgs = (input.arguments ?? "").trim();
  if (!rawArgs) {
    output.parts = [{
      type: "text" as const,
      text: "**Usage:** `/explain <file path or code snippet>` — get an AI explanation of the code.",
    }] as never;
    return;
  }
  try {
    const result = await sdkFusionDispatch(
      client,
      `Explain the following code clearly and concisely:\n\n${rawArgs}`,
      ["deepseek-v4-pro"],   // single model for explanation
      undefined,             // default synthesis model
      0.1,                   // cost ceiling
    );
    output.parts = [{
      type: "text" as const,
      text: `**📖 Code Explanation**\n\n${result.fused_answer}`,
    }] as never;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    output.parts = [{
      type: "text" as const,
      text: `❌ /explain failed: ${msg}`,
    }] as never;
  }
  return;
}
```

**Acceptance Criteria**:
- `/explain` works without the companion (uses SDK dispatch directly)
- No reference to `fusion_dispatch_tool` MCP tool in the plugin
- `/explain` output format preserved (📖 emoji, clean explanation text)

**QA**:
1. Type `/explain "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)"` → gets explanation
2. Verify no relay calls in the console output for `/explain`
3. Verify `/explain` with no args shows usage help

---

### Wave 3: Dual Companion Consolidation

#### Task 3.1: Remove MCP companion config from opencode.json
**Priority**: High | **Dependencies**: All fusion removal tasks (2.1-2.5), classifier fix (1.2)

**File**: `~/.config/opencode/opencode.json`

**Changes**: Remove the `"bifrost-companion"` entry from the `"mcp"` block:

```jsonc
// BEFORE:
"mcp": {
  "bifrost-companion": {
    "type": "local",
    "command": ["python3", "/sibcb1/chuyanyilab1/tangjunjie/skills-repo/bifrost/companion/server.py"],
    "enabled": true
  }
}
// AFTER:
"mcp": {}
```

Or remove the entire `"mcp"` key if `bifrost-companion` is the only entry.

**Acceptance Criteria**:
- OpenCode no longer spawns a companion process
- Plugin continues to work (it manages its own companion via `mcp-relay.ts`)
- No `python3 .../server.py` process running from OpenCode's MCP system
- Agent tools (memory, classifier, etc.) are NOT listable as MCP tools — they're used through the plugin's hooks

**QA**:
1. Start OpenCode with the updated config
2. `ps aux | grep server.py` → exactly ONE process (plugin-spawned)
3. Plugin hooks work: `tool.execute.before` classifies tools, `compacting` saves memory
4. Slash commands work: `/goal`, `/review`, `/commit`, `/test`, `/audit-permissions`, `/explain`

---

#### Task 3.2: Remove `configure` call from plugin init
**Priority**: Medium | **Dependencies**: Task 2.1 (configure removed from companion)

**File**: `bifrost/plugin/index.ts` lines 610-614

**Changes**: Remove the configure call from plugin initialization:

```typescript
// BEFORE (lines 610-614):
try {
  await relay.call("configure", { server_url: pluginInput.serverUrl.toString() });
  console.log("[bifrost] configured companion with server_url:", pluginInput.serverUrl.toString());
} catch (err) {
  console.warn("[bifrost] configure failed (non-fatal):", err);
}

// AFTER: (entire block removed — configure tool no longer exists)
```

Also check: the `FusionResult` interface (lines 33-50) and `formatFusionOutput` function (lines 154-224) are still needed because they're used by `sdkFusionDispatch` in the plugin (for `/fusion` slash command and the `fusion` tool). **Do NOT remove these.**

**Acceptance Criteria**:
- Plugin starts without attempting to call `configure`
- No `configure failed` warning in logs
- Plugin hooks still work (classifier, goal, skill, audit, memory)

**QA**:
1. Start OpenCode with plugin loaded
2. Check logs: no `configure` messages
3. Verify `tool.execute.before` still classifies tool calls

---

### Wave 4: Verification & Cleanup

#### Task 4.1: Verify chat.message hook fix
**Priority**: Low | **Dependencies**: None (verification only)

**File**: `bifrost/plugin/index.ts` line 1083

**Current code**:
```typescript
const text = (output.parts?.find(p => p.type === "text") as any)?.text ?? "";
```

**Verification**: Confirm this correctly reads the user's `/fusion` or `/goal` command text from `output.parts`. The `chat.message` hook fires when the agent sends a message. The user's input text appears in `output.parts` as text parts.

**Acceptance Criteria**:
- `/fusion "test"` correctly extracts `"test"` as the prompt
- `/goal "do something"` correctly extracts `"do something"` as the goal
- Empty `/fusion` shows usage help

**QA**:
1. Type `/fusion "hello"` → dispatches to models with prompt "hello"
2. Type `/goal "fix lint"` → runs goal loop with goal "fix lint"
3. Type `/fusion` with no args → shows usage help

**Status**: ✅ Already fixed. Should be verified during full integration test.

---

#### Task 4.2: Full integration test
**Priority**: High | **Dependencies**: All tasks above

**Test scenarios**:

1. **Companion lifecycle**:
   - Plugin starts → companion spawned (exactly one process)
   - Health monitor pings companion every 30s
   - Companion crash → health monitor restarts it
   - Plugin dispose → companion process killed

2. **Classifier**:
   - `Bash ls` → ALLOW (allowlisted)
   - `Bash cargo build` → ALLOW (default, not destructive)  
   - `Bash rm -rf /tmp/foo` → DENY (destructive)
   - `Read file.md` → ALLOW (read-only, fast path)
   - `Write file.md` → ASK_USER (write tool)
   - `Edit file.md` → ASK_USER (write tool)

3. **Memory** (plugin-initiated):
   - Session compaction saves decision memory
   - Tool errors save feedback memory

4. **Slash commands**:
   - `/goal "test"` → runs simulation with classifier
   - `/review` → loads review skill
   - `/explain "code"` → uses SDK dispatch (not companion)
   - `/audit-permissions` → outputs migration block

5. **Fusion** (plugin SDK dispatch):
   - `/fusion "hello"` → dispatches to models via SDK (not companion)
   - `fusion` tool → same as above

6. **NFS bytecode**:
   - No `__pycache__` under `bifrost/companion/` after startup
   - Source edits take effect on next companion restart

---

## Dependency Graph

```
Wave 1 (parallel, no deps):
  T1.1 (NFS fix)  ────┐
  T1.2 (Bash fix)  ────┤
                        │
Wave 2 (sequential):    │
  T2.1 (remove configure) ──┐
  T2.2 (remove fusion tool) ─┤ (depends on T2.1)
  T2.3 (delete dispatch.py)  ┤ (depends on T2.1, T2.2)
  T2.4 (remove fusion config)┤ (depends on T2.3)
  T2.5 (rewrite /explain)    ┘ (depends on T2.1, T2.2)
                              │
Wave 3 (after Wave 2):       │
  T3.1 (remove MCP config)  ─┤ (depends on all Wave 2)
  T3.2 (remove plugin configure call) ─┤ (depends on T2.1)
                                        │
Wave 4 (after all above):              │
  T4.1 (verify chat.message)  ◄────────┘
  T4.2 (integration test)     ◄────────┘
```

### Parallel execution strategy

**Batch A** (start immediately, run in parallel):
- T1.1 (NFS bytecode cache fix) — `mcp-relay.ts` + `server.py`
- T1.2 (Classifier bash fix) — `classifier.py`

**Batch B** (after Batch A, sequential within):
- T2.1 → T2.2 → T2.3 → T2.4 → T2.5 (fusion removal chain)

**Batch C** (after Batch B):
- T3.1 (opencode.json)
- T3.2 (plugin configure call)

**Batch D** (after Batch C):
- T4.1 (verify)
- T4.2 (integration test)

---

## Todos

### Wave 1 (Parallel — no dependencies)
1. [x] Fix NFS bytecode cache staleness
2. [x] Fix classifier blocking Bash commands

### Wave 2 (Sequential — fusion removal)
3. [x] Remove `configure` MCP tool, `_openode_server_url`, fix ImportError
4. [x] Remove `fusion_dispatch_tool` MCP tool
5. [x] Delete companion/fusion/ directory
6. [x] Remove fusion-related config defaults
7. [x] Rewrite `/explain` slash command to use SDK dispatch

### Wave 3 (After Wave 2)
8. [x] Remove MCP companion config from opencode.json
9. [x] Remove configure call from plugin init

### Wave 4 (Verification)
10. [x] Verify chat.message hook fix
11. [x] Full integration test

## Final Verification Wave
- [x] F1. Companion starts without ImportError
- [x] F2. Classifier allows bash, blocks destructive commands
- [x] F3. All companion tools (memory, classifier, goal, skill, audit) work
- [x] F4. `/fusion` works via task() dispatch (not companion)
- [x] F5. No duplicate companion processes
- [x] F6. NFS bytecode cache is fresh on each start
- [x] F7. chat.message hook correctly reads user slash commands

## Verification Strategy

### Per-task verification (during implementation)

| Task | Unit verification |
|------|------------------|
| T1.1 | `echo $PYTHONDONTWRITEBYTECODE` in spawn env, `__pycache__` deletion confirmed |
| T1.2 | Call classifier with various bash commands, check response time |
| T2.1 | `grep -r "configure\|_openode_server_url" companion/server.py` → no results |
| T2.2 | List MCP tools → no `fusion_dispatch_tool` |
| T2.3 | `ls companion/fusion/` → "No such file" |
| T2.4 | `python3 -c "from companion.config import load_config; c = load_config(); print(hasattr(c, 'fusion_models'))"` → False |
| T2.5 | `/explain "code"` works via SDK dispatch |
| T3.1 | `ps aux \| grep server.py` → exactly one process |
| T3.2 | No `configure` log messages |
| T4.1 | `/fusion`, `/goal` slash commands work correctly |
| T4.2 | Full manual test of all features |

### Post-implementation verification

1. **Build**: `cd bifrost/plugin && npx tsc --noEmit` → no errors
2. **LSP diagnostics**: `lsp_diagnostics` on `server.py`, `classifier.py`, `config.py`, `index.ts`, `mcp-relay.ts` → clean
3. **Python syntax**: `python3 -m py_compile companion/server.py companion/classifier/classifier.py companion/config.py` → clean
4. **Companion startup**: `python3 companion/server.py` → starts without ImportError
5. **OpenCode startup**: Start OpenCode → plugin loads, no duplicate companion, all features work
6. **No regression**: All existing MCP tools (memory, classifier, goal, skill, audit) still work

---

## Files Summary

| File | Action | Lines affected |
|------|--------|---------------|
| `bifrost/plugin/mcp-relay.ts` | Edit | ~329 (add `PYTHONDONTWRITEBYTECODE`) |
| `bifrost/companion/server.py` | Edit | 1-17 (cache cleanup), 24 (remove import), 41-42 (remove global), 125-131 (remove configure), 186-210 (remove fusion_dispatch_tool) |
| `bifrost/companion/classifier/classifier.py` | Edit | 356-379 (bash default → ALLOW) |
| `bifrost/companion/config.py` | Edit | 20-22 (remove fusion defaults) |
| `bifrost/companion/fusion/` | Delete | Entire directory (585 lines in dispatch.py + __init__.py) |
| `bifrost/plugin/index.ts` | Edit | 610-614 (remove configure call), 899-945 (rewrite /explain) |
| `~/.config/opencode/opencode.json` | Edit | Remove `bifrost-companion` from `mcp` block |
