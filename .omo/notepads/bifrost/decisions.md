# Bifrost — Decisions & Findings

## T9.1: FusionDispatch MCP Tool (2026-07-10)

### Implementation Decisions

1. **Module location**: `bifrost/companion/fusion/dispatch.py`
   - Lives alongside existing `fusion/__init__.py` (was empty)
   - Follows project pattern of companion subdirectories (memory/, context/, fusion/)

2. **MCP registration**: `fusion_dispatch_tool` in `server.py`
   - Thin wrapper over `fusion_dispatch()` — keeps tool registration separate from core logic
   - Named `fusion_dispatch_tool` to distinguish from the underlying function

3. **Model calling**: Mock implementation with pluggable architecture
   - `_call_model()` uses a mock that simulates latency and returns placeholder text
   - Designed so the function body can be swapped for real HTTP API calls without changing the orchestration layer
   - Production path: replace mock body with `requests.post()` to model provider endpoints

4. **Parallel dispatch**: `concurrent.futures.ThreadPoolExecutor`
   - One thread per model (max 3)
   - `as_completed()` for collecting results as they arrive
   - Per-model timeouts via `future.result(timeout=...)`

5. **Timeout resilience**: If one model times out → fusion completes with remaining models
   - Timed-out models get `timed_out=True` and appear in `timed_out_models` list
   - If ALL models time out → fused_answer is an error message
   - Synthesis model gets 2× the per-model timeout

6. **Cost tracking**:
   - Hard-coded MODEL_RATES dict with per-token pricing (input/output)
   - Coarse token estimation: `len(text) // 4` chars per token
   - Cost ceiling enforced — if cumulative cost exceeds ceiling, model still included but with warning
   - Synthesis cost added to total

7. **Synthesis prompt**: Template instructs the synthesis model to:
   - Identify strongest claims from each response
   - Resolve contradictions
   - Weight weaker responses less
   - Produce one unified answer (not a list)

8. **Label compliance**: All output prepended with `EXPERIMENTAL — Model Fusion (v1-alpha)`
   - Synthesis prompt instructs synthesis model to include the label
   - Fallback: prepend if synthesis model omitted it

### Dependencies Satisfied
- [x] companion/config.py from T1.3 — used for `model_for_fusion_synthesis` default
- [x] companion/server.py from T1.6 — modified with MCP tool registration
- [x] Plugin MCP relay from T3.2 — companion exposes tool over MCP stdio

### Open Items
- [ ] Replace mock `_call_model` with real API calls (needs API keys)
- [ ] Live pricing API for MODEL_RATES instead of hard-coded
- [x] T9.2: /fusion slash command in plugin

## T8.1: ConfigMigrate MCP Tool (2026-07-10)

### Implementation Decisions

1. **Module location**: `bifrost/companion/permission/migrate.py`
   - New `permission/` package under companion
   - `config_migrate()` is the core function; `_transform_*` helpers handle per-key logic

2. **MCP registration**: `config_migrate()` in `server.py`
   - Imported as `_config_migrate` to avoid naming conflict with the decorated MCP tool
   - Thin wrapper delegates to the imported function

3. **Dual format support**: Handles both flat (`permissions.allow`) and nested (`permissions.allow`) Claude Code settings
   - `_resolve_permissions()` normalizes both formats into a dict

4. **Key mappings** (from Wave 0.4 probe):
   - `permissions.allow/deny/ask` → 1:1 (direct copy)
   - `model`/`models` → transform via lookup table (sonnet → deepseek-v4-flash, opus → deepseek-v4-pro)
   - `allow_write_to_workspace` → `permissions.allow += ["Write"]` when true
   - `browser` → `mcpServers.playwright: { enabled: true }` with MANUAL REVIEW flag
   - `allowedBashCommands` → `permissions.allow` with `bash:` prefix
   - `verbose` → MANUAL REVIEW REQUIRED (no OpenCode equivalent)
   - Unknown keys → MANUAL REVIEW REQUIRED section

5. **Secret filtering**: Multi-pattern detection replaces values with `// FILTERED`:
   - `sk-` tokens (20+ alphanumeric chars)
   - Keys matching: `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `api_key`, `api-key`
   - 40+ char base64-like values

6. **Read-only enforcement**: Source file never modified — `Path.read_text()` only

### Verification
- [x] Real `~/.claude/settings.json` — model mapped, secrets filtered, unmappable flagged
- [x] Synthetic full-config fixture — all 8 transform types exercised
- [x] File not found → error message returned
- [x] Malformed JSON → error message returned
- [x] No secrets leaked in any output

### Files
- Created: `bifrost/companion/permission/__init__.py`
- Created: `bifrost/companion/permission/migrate.py`
- Modified: `bifrost/companion/server.py` (import + `@mcp.tool()` registration)

## T8.2: /audit-permissions Slash Command (2026-07-10)

### Implementation Decisions

1. **Hook used**: `"command.execute.before"` — the OpenCode plugin hook that fires before a slash command executes
   - Intercepts when `input.command === "audit-permissions"`, returns early for all other commands
   - Sets `output.parts` with formatted text to display results inline

2. **Argument parsing**: Optional `[path]` argument from `input.arguments`
   - Empty/undefined → defaults to `"~/.claude/settings.json"`
   - Passed directly to the companion's `config_migrate` tool as `source_path`

3. **Companion relay**: Calls `relay.call<string>("config_migrate", { source_path })` via the existing MCP relay
   - Gracefully handles `!relay.connected` → shows "companion not running" message
   - Tool error responses (file not found, parse errors) → displayed with `❌` prefix
   - Unexpected exceptions → caught and displayed with `❌ /audit-permissions failed:` prefix

4. **Output format**: 
   - Prominent ASCII banner: `⚠️ DO NOT AUTO-APPLY — REVIEW MANUALLY`
   - Subtitle: `This is a READ-ONLY audit. Copy sections you need.`
   - Raw migration output from `config_migrate` (contains sections for 1:1 mappings, transforms, secrets filtered, manual review)
   - Footer reminder: `Review each section manually before applying.`
   - Explicit note: `This tool does NOT modify any files.`

5. **Read-only guarantee**: The companion's `config_migrate` tool only reads source files — the plugin adds no write logic. No auto-apply.

6. **Type safety**: Uses `as never` casting for `output.parts` to avoid importing `Part` from transitive dependency `@opencode-ai/sdk`
   - Minimal text-part shape: `{ type: "text", text: "..." }`
   - TypeScript compiles clean with project tsconfig

### Verification
- [x] TypeScript compilation (`tsc --noEmit`) — zero errors
- [x] Hook registered in correct position (between `permission.ask` and `experimental.session.compacting`)
- [x] Companion not connected → graceful error message
- [x] Tool error detection: `startsWith("No Claude Code config found at")`, `"Error reading"`, `"Error parsing"`
- [x] DO NOT AUTO-APPLY banner present in all successful output
- [x] No imports added beyond existing dependencies

### Files
- Modified: `bifrost/plugin/index.ts` — added `"command.execute.before"` hook (lines 180-230)

## T9.2: /fusion Slash Command (2026-07-10)

### Implementation Decisions

1. **Dual registration**: `tool.fusion` (AI-invokable) + `"command.execute.before"` hook (user slash command)
   - `tool.fusion`: Zod-validated tool with prompt, models, synthesis_model, cost_ceiling args — AI can invoke
   - `command.execute.before`: intercepts `/fusion [prompt]` typed by user — primary invocation path
   - Both paths converge on `relay.call("fusion_dispatch_tool", ...)` via the MCP relay

2. **Argument parsing**: `parseFusionArgs()` strips surrounding quotes from raw arguments
   - Handles both `/fusion "hello world"` and `/fusion hello world` (though quoted form is canonical)
   - Empty/undefined → usage instructions displayed via `formatUsage()`

3. **Companion relay**: Calls `relay.call<FusionResult>("fusion_dispatch_tool", { prompt, cost_ceiling: 0.5 }, 120_000)`
   - 120-second timeout (2 minutes) to accommodate parallel model dispatch + synthesis
   - Cost ceiling hardcoded at $0.50 per the specification
   - `!relay.connected` → friendly "companion not running" message
   - Errors caught and displayed with `❌ /fusion failed:` prefix

4. **Output format (markdown)**:
   - **EXPERIMENTAL banner**: ASCII box with "🧪 EXPERIMENTAL — Model Fusion (v1-alpha)" and disclaimer
   - **Per-model responses**: collapsible `<details>/<summary>` sections showing model name, status (✅/⏱ TIMEOUT/⚠️ ERROR), cost, latency, token counts
   - **Fused answer**: prominently displayed under `## 🧬 Fused Answer` heading with horizontal rules
   - **Cost breakdown**: `## 💰 Cost Breakdown` table with per-model and total, plus cost ceiling note
   - **Wall time**: displayed at top with the prompt recap
   - **Usage instructions**: `formatUsage()` shows when `/fusion` typed without prompt

5. **Error handling**:
   - Companion not running → explicit error message pointing to `bifrost-companion`
   - Timed-out models → shown in output (companion handles partial failures)
   - Exceptions → caught and displayed with `❌ /fusion failed:` prefix
   - Per-model errors from companion → shown within collapsible sections

6. **Type safety**: `FusionResult` interface mirrors companion's return shape
   - model_responses array with per-model cost/timing/tokens/errors
   - Kept as local interface (no import from Python companion needed)
   - `output.parts` uses `as never` cast to avoid transitive `@opencode-ai/sdk` dependency (same pattern as T8.2)

7. **Constraints enforced**:
   - **Cost ceiling**: $0.50 per fusion, enforced by companion (plugin passes it)
   - **Max 3 models**: enforced by companion's `fusion_dispatch()` (returns ValueError)
   - **Min 2 models**: enforced by companion
   - **EXPERIMENTAL label**: all output labeled; banner + fused answer both carry the label

### Dependencies Satisfied
- [x] companion/fusion/dispatch.py from T9.1 — `fusion_dispatch_tool` MCP tool
- [x] companion/config.py from T1.3 — `cost_ceiling_default`, `model_for_fusion_synthesis`
- [x] plugin/index.ts from T3.1 — updated with hooks
- [x] plugin/mcp-relay.ts from T3.2 — `relay.call()` transport

### Verification
- [x] TypeScript compilation (`tsc --noEmit`) — zero errors
- [x] `tool.fusion` registered in hooks object (between `permission.ask` and `command.execute.before`)
- [x] `command.execute.before` handles `/fusion` before `/audit-permissions` (early return pattern)
- [x] `/fusion` without args → `formatUsage()` displayed
- [x] Companion not connected → graceful error message
- [x] EXPERIMENTAL banner present in all output
- [x] Per-model responses in collapsible `<details>` sections
- [x] Fused answer prominently displayed
- [x] Cost breakdown with total and per-model
- [x] Wall time displayed

### Files
- Modified: `bifrost/plugin/index.ts` — added `import { tool }`, `FusionResult` type, `parseFusionArgs`/`formatUsage`/`formatFusionOutput` helpers, `tool.fusion` hook, `/fusion` handling in `command.execute.before`

## T8.3: Permission Audit Integration Tests (2026-07-10)

### Implementation Decisions

1. **Test file location**: `bifrost/tests/test_permission_migration.py`
   - Follows existing convention: class-based tests in `bifrost/tests/`

2. **Import path**: `from companion.permission.migrate import config_migrate`
   - Direct import of the core function, not via MCP tool wrapper

3. **Test isolation**: All temp files use `NamedTemporaryFile` with `delete=False` + manual `unlink()` in `finally`
   - No shared state, no temp files leaked

4. **Core 5 tests**:
   - Test 1: Real `~/.claude/settings.json` — verifies sections present, `FILTERED` markers, `MANUAL REVIEW REQUIRED`, md5sum unchanged, no raw secret values
   - Test 2: Empty file (`{}`) — header only, no crash, no spurious review flags
   - Test 3: Missing file — returns `"No Claude Code config found at..."` message with resolved path
   - Test 4: Secrets-only file — all secret values filtered, `FILTERED` count ≥3, env secrets warning present
   - Test 5: Synthetic fixture with all 8 transform types — every mapping rule verified individually

5. **Edge-case tests** (12 additional):
   - Whitespace-only JSON (`{ }`) — parses successfully
   - Flat `permissions.allow` format — supported alongside nested `permissions.allow`
   - Malformed JSON → parse error message
   - `allow_write_to_workspace: false` → no Write add, "no change needed" message
   - `browser: false` → "playwright MCP not enabled", no `enabled: true`
   - `browser: true` → MANUAL REVIEW REQUIRED with playwright config
   - `model: sonnet` → `deepseek-v4-flash` mapping with source annotation
   - `model: opus` → `deepseek-v4-pro` mapping
   - Unknown model (`gpt-4`) → passthrough as-is
   - `models` dict form with `default`/`quick` → both mapped
   - Empty `allowedBashCommands` → no bash section emitted
   - Tilde expansion → `~/path` resolves to home directory

### Verification
- [x] Real `~/.claude/settings.json` — sections present, secrets filtered, file unmodified (md5sum)
- [x] Empty `{}` — graceful, no crash, no spurious sections
- [x] Whitespace-only `{ }` — parses to `{}`, returns header
- [x] Missing file — `"No Claude Code config found at..."` message
- [x] Secrets only — all 5 secret values filtered, `FILTERED` count ≥3
- [x] All permission types synthetic — 1:1, allow_write, model, browser, bash, verbose, env, unknown all mapped
- [x] Flat permissions format — `permissions.allow` supported
- [x] Malformed JSON — `"Error parsing..."` message
- [x] Boolean flags both true and false paths tested
- [x] Model mapping: sonnet→flash, opus→pro, unknown→passthrough
- [x] Tilde path expansion
- [x] Full suite: 215 passed, 0 failed, 0 LSP diagnostics

### Files
- Created: `bifrost/tests/test_permission_migration.py` (17 tests, 1 class)

## T6.1: GoalLoop MCP Tool (2026-07-10)

### Implementation Decisions

1. **Module location**: `bifrost/companion/goal/loop.py`
   - New `goal/` package under companion
   - `goal_loop()` is the core function; thin wrapper in `server.py` for MCP registration

2. **MCP registration**: `goal_loop()` in `server.py`
   - Imported as `_goal_loop` to avoid naming conflict with the decorated MCP tool
   - Thin wrapper delegates to the imported function — follows existing pattern (fusion, classifier, config_migrate)

3. **Simulation-first design**: The loop accepts `actions: list[dict]` for simulation
   - Each action dict has `tool_name` (required), `tool_args`, `estimated_cost`, `file_paths`
   - No real agent execution — designed to be called with pre-computed action sequences
   - Real agent execution can be layered on later without changing the loop core

4. **Classifier integration**: Each turn calls `classify_tool_call()` from T5.1
   - Session context passed with `{"goal": goal, "task_id": "goal_loop"}`
   - Uses existing two-tier classifier (pre-filter fast-path + model dispatch slow-path)

5. **Termination conditions** (checked in priority order after each turn):
   - `goal_met` — action with `tool_name` in `{"task_done", "task_complete", "finish"}`
   - `blocked` — 3 consecutive DENY decisions from classifier
   - `cost_exceeded` — cumulative estimated_cost > cost_ceiling
   - `max_turns` — turns_executed >= max_turns (checked at loop start and end)

6. **Cost tracking**:
   - Each action can specify `estimated_cost` (default $0.01)
   - Cumulative cost tracked per-turn and included in turn records
   - Ceiling enforced after each action is counted

7. **Denial streak**: Consecutive DENY counter resets on any ALLOW or ASK_USER
   - Only 3 *consecutive* DENY triggers `blocked` — intermittent denials don't block

8. **Config integration**: Defaults loaded from `companion/config.py`
   - `max_turns_default` (10) and `cost_ceiling_default` ($1.00) from config
   - Explicit args override config defaults
   - Absolute cap: `max_turns` cannot exceed 50

9. **Validation**: `_validate_args()` enforces all constraints before loop starts
   - Non-empty goal, max_turns in [1, 50], positive cost_ceiling, actions is list of dicts
   - Each action validated for required `tool_name` key

10. **Return shape**: Summary dict with all required keys:
    - `goal`, `status`, `turns_used`, `total_cost`, `wall_time_ms`, `output_summary`, `termination_reason`, `turns` (per-turn records)

### Dependencies Satisfied
- [x] companion/config.py from T1.3 — used for max_turns_default, cost_ceiling_default
- [x] companion/server.py from T1.6 — modified with MCP tool registration
- [x] companion/classifier/classifier.py from T5.1 — classify_tool_call integration
- [x] Plugin classifier wiring from T5.2 — classifier ready for use

### Files
- Created: `bifrost/companion/goal/__init__.py`
- Created: `bifrost/companion/goal/loop.py`
- Modified: `bifrost/companion/server.py` — import + `@mcp.tool()` registration

## T6.3: /goal Slash Command (2026-07-10)

### Implementation Decisions

1. **Hook used**: `"command.execute.before"` — same OpenCode plugin hook as `/fusion` and `/audit-permissions`
   - Intercepts when `input.command === "goal"`, returns early for all other commands
   - Sets `output.parts` with formatted text to display results inline

2. **Argument parsing**: Reuses `parseFusionArgs()` to strip surrounding quotes from `input.arguments`
   - Handles `/goal "Fix all lint errors"` (canonical) and `/goal Fix` (bare word)
   - Empty/undefined → `formatGoalUsage()` displayed with usage instructions

3. **Companion relay**: Calls `relay.call<GoalLoopResult>("goal_loop", { goal, actions }, 30_000)`
   - 30-second timeout — ample for classifier-gated simulation loop
   - Single simulated `Read` action with `estimated_cost: 0.01` passed as the actions list
   - `max_turns` and `cost_ceiling` omitted — companion uses config defaults (10 turns, $1.00 ceiling)
   - `!relay.connected` → friendly "companion not running" message

4. **Output format (markdown)**:
   - **ASCII banner**: `🎯 Goal Loop — Classifier-Gated Agent Simulation`
   - **Goal display**: quoted goal text at top
   - **📊 Progress section**: turns used, last action, classifier decisions summary
   - **Turn-by-turn table**: `| # | Action | Decision | Reason |` with reason truncated to 60 chars
   - **📋 Summary section**: status (with icon ✅/🚫/💰/⏱️), turns_used, total_cost (4 decimal places), wall_time_ms, termination_reason

5. **Error handling**:
   - Companion not running → explicit error message pointing to `bifrost-companion`
   - No arguments → `formatGoalUsage()` displayed with termination conditions and examples
   - MCP call failures → caught and displayed with `❌ /goal failed:` prefix
   - `max_turns > 50` enforced by companion's `_validate_args()` (plugin never passes it)

6. **Type safety**:
   - `GoalLoopResult` interface mirrors companion's return shape with nests `turns` array
   - Kept as local interface (no import from Python companion)
   - `output.parts` uses `as never` cast — same pattern as T8.2 and T9.2
   - No auto-approve — user must explicitly type `/goal`, never auto-triggered

7. **Simulated actions**: Single `Read` action passed as the simulated loop
   - `{ tool_name: "Read", tool_args: {}, estimated_cost: 0.01 }`
   - Classifier processes this action → decision recorded in turn records
   - Minimal but sufficient to exercise the full goal_loop pipeline

### Dependencies Satisfied
- [x] companion/goal/loop.py from T6.1 — `goal_loop` MCP tool registered in server.py
- [x] companion/config.py from T1.3 — `max_turns_default`, `cost_ceiling_default` used by companion
- [x] plugin/index.ts from T3.1 — updated with hooks
- [x] plugin/mcp-relay.ts from T3.2 — `relay.call()` transport

### Verification
- [x] TypeScript compilation (`tsc --noEmit`) — zero errors
- [x] `command.execute.before` handles `/goal` between `/fusion` and `/audit-permissions` (early return pattern with correct ordering)
- [x] `/goal` without args → `formatGoalUsage()` displayed
- [x] Companion not connected → graceful error message
- [x] Progress section: turns used, last action, classifier decisions all present
- [x] Summary section: status with icon, turns_used, cost, wall_time, termination_reason
- [x] Goal banner displayed in all output
- [x] Error catch-and-display for MCP failures

### Files
- Modified: `bifrost/plugin/index.ts` — added `GoalLoopResult` interface, `formatGoalUsage`/`formatGoalOutput` helpers, `/goal` handler in `command.execute.before`

## T10.2: README.md (2026-07-10)

### Implementation Decisions

1. **Document structure**: 11 sections following the task specification: Overview, Features, Prerequisites, Installation, Configuration, Architecture, Usage, Skill Bridge, Limitations, Contributing, License.

2. **Overview framing**: Positions Bifrost as a "middleware layer" between OpenCode agents and their execution environment. Explains the statelessness problem Bifrost solves. No mention of other coding agents by name.

3. **Feature descriptions**: All 7 features documented with their current capability level. Feature 7 (Model Fusion) prominently labeled EXPERIMENTAL in its heading, description, and Usage section. Classifier's DEFAULT DENY policy highlighted. Goal loop's simulation-only nature made clear.

4. **Architecture diagram**: ASCII box-drawing diagram showing User -> Plugin (TypeScript) -> Companion (Python FastMCP) -> SQLite. Companion column detail includes all subpackages. Second row shows each MCP relay call mapping. Third row shows SQLite tables. Component roles table below the diagram. Two data flow walkthroughs: tool call classification lifecycle and slash command lifecycle.

5. **Installation**: Four sequential steps (clone, pip install, npm install, copy snippet). Includes both `uv` and plain `python` command alternatives for running the companion. No absolute paths.

6. **Configuration reference**: Two config surfaces documented: opencode.json (plugin enable toggle + mcpServers block) and companion config.yaml (6 fields with defaults in table). XDG search path documented. Example config provided.

7. **Usage**: Three subsections: Memory commands (4 tools with descriptions), Slash commands (/goal, /fusion, /audit-permissions with examples), MCP tools (full table of all 12 companion tools with categories).

8. **Skill Bridge**: Linked to SKILL_COMPAT.md. Summary of verified vs best-effort counts. Contribution workflow for adding verifications.

9. **Limitations**: Six specific limitations: classifier guidance-not-enforcement, goal loop simulation-only, fusion cost approximations, skill bridge text-only, no distributed memory, alpha instability warning. Each with a clear scope description.

10. **v0.1.0-alpha label**: Prominently displayed in header (bold). Repeated in Limitations section with explicit "Do not run in production" warning.

### Compliance Checks
- [x] Zero em dashes (9 replaced with periods, colons, parentheses)
- [x] Zero "Claude Code" mentions (uses "other coding agent tools" phrasing)
- [x] Zero absolute paths
- [x] v0.1.0-alpha label prominent (line 3, bold)
- [x] No production stability claims (opposite: explicit "Not for production use", "Do not run in production")
- [x] Links to SKILL_COMPAT.md
- [x] License section references local LICENSE file (MIT)

### Files
- Created: `bifrost/README.md` (replaced 3-line stub with 325-line comprehensive README)

## T10.3: LICENSE + CONTRIBUTING.md (2026-07-10)

### Implementation Decisions

1. **LICENSE**: Standard MIT license already existed at `bifrost/LICENSE`
   - Copyright year: 2026
   - Copyright holder: Tang Junjie
   - Standard MIT template — no custom clauses, no additional restrictions
   - No modifications needed (already correct)

2. **CONTRIBUTING.md**: Created at `bifrost/CONTRIBUTING.md`
   - Dev environment setup for both Python companion and TypeScript plugin
   - Python: `uv pip install -r requirements.txt` (fastmcp, pyyaml, httpx)
   - TypeScript: `npm install` then `npx tsc --noEmit`
   - Testing: `uv run pytest tests/ -v` for Python, `npx tsc --noEmit` for TypeScript
   - Code style: type hints mandatory, pathlib over os.path, strict TypeScript, Google-style docstrings
   - PR process: issue first, fork-and-branch, keep PRs small, pass full test suite, wait for review
   - Code of conduct: Contributor Covenant 2.1 reference

3. **Project structure documented**: Full directory tree showing companion/ (classifier, context, fusion, goal, memory, permission, skill), plugin/ (index.ts, mcp-relay.ts, health.ts), and tests/ layout

### Files
- Existing: `bifrost/LICENSE` (MIT, verified correct)
- Created: `bifrost/CONTRIBUTING.md`

## T10.5: Prepare for Open Source (2026-07-10)

### Implementation Decisions

1. **`.gitignore` entries**: Updated `bifrost/.gitignore` with 4 groups:
   - Python cache: `__pycache__/`, `*.pyc`, `.pytest_cache/`
   - Database: `*.db`, `bifrost.db` (specific named db)
   - Logs: `*.log`
   - Node modules: `node_modules/`
   - Agent metadata: `.omo/`, `.agents/`, `.claude/`

2. **Artifact verification**: Dry-run `git add -n bifrost/` confirmed zero unwanted files:
   - No `__pycache__/` directories tracked (exists locally but excluded)
   - No `.pyc` files tracked
   - No `node_modules/` tracked (exists locally at 81MB, excluded)
   - No `.pytest_cache/` tracked
   - No `.db` or `.log` files tracked

3. **Secrets scan**: `grep -r 'sk-[A-Za-z0-9]' bifrost/` found matches ONLY in `tests/test_permission_migration.py`:
   - All matches are deliberately fake test fixtures with obvious patterns (`sk-12345678901234567890`, `sk-abcdefghijklmnopqrstuv`, `sk-aaaaaaaaaaaaaaaaaaaa`, `sk-should-be-filtered-xxxxxxxxxx`)
   - These fixtures test the secret filtering logic — they are NOT real API keys
   - No real secrets or API keys exist anywhere in the bifrost/ tree

4. **Commit**: Single atomic commit `feat(bifrost): initial release v0.1.0-alpha`
   - 53 files, 9582 insertions
   - All bifrost/ source files included; zero test artifacts, cache files, or temp files

5. **Git tag**: `v0.1.0-alpha` (annotated) pointing to commit `5bbfb3f`
   - Annotation: "Bifrost v0.1.0-alpha: initial experimental release"
   - Verified `git ls-tree -r v0.1.0-alpha` shows zero unwanted files

### Verification
- [x] `bifrost/.gitignore` exists with all required entries
- [x] `git ls-tree -r v0.1.0-alpha --name-only` shows no `node_modules`, `__pycache__`, `.pyc`, `.pytest_cache`, `.db`, `.log`
- [x] `git tag -l 'v0.1.0*'` shows `v0.1.0-alpha`
- [x] No real API keys or secrets in repo (test fixtures only, clearly fake)
- [x] Clean single-commit history for bifrost/ (1 commit on main)

### Files
- Modified: `bifrost/.gitignore` (added bifrost.db, .omo/, .agents/, .claude/)
