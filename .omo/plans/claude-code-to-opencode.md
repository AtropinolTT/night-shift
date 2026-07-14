# claude-code-to-opencode - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** Bifrost — an open-source OpenCode plugin that brings 7 features from other coding agents to OpenCode: persistent memory across sessions, automatic project context loading, a safety classifier that guards every tool call, continuous goal-driven agent loops, skill compatibility bridging, read-only permission migration, and experimental model fusion.

**Why this approach:** Plugin + companion architecture over MCP — the plugin hooks into OpenCode's event system (session start, before every tool call, on context compaction), and a lightweight Python companion handles the actual memory storage, skill loading, and model dispatch. This split keeps the JS plugin thin (~300 lines) and puts all heavy logic in Python where it's easier to test and maintain. SQLite instead of JSON files means memory survives concurrent sessions and scales beyond a few hundred entries.

**What it will NOT do:** Run shell commands from skill files (blocked for security). Auto-approve any file writes (classifier always asks first). Touch your existing Claude Code configuration. Claim all 76 skills work perfectly — 10 are verified, the rest are honest best-effort. Replace OpenCode's built-in systems — it extends them, not replaces them.

**Effort:** Large (11 waves, 54 todos, ~3000 lines of new code across Python + TypeScript)
**Risk:** Medium — core architecture (MCP over stdio, SQLite, FastMCP) is proven; highest risk is OpenCode hook API stability and classifier latency
**Decisions I made for you:** SQLite over JSON (concurrency-safe), read-only permission migration (no silent config changes), DEFAULT DENY classifier (never auto-approves writes), 10 verified skills (not 76), model fusion labeled experimental, classifier learning is feedback logging only (no auto-apply), no nano-claude-code fork (clean-room implementation), companion in Python + FastMCP (not JS), MIT license for open source

Your next move: Approve this plan, then run `/start-work` to begin execution. Full execution detail follows below.

---

> TL;DR (machine): Large effort, 54 todos across 11 waves — OpenCode plugin + Python companion bringing memory/context/classifier/goal-loop/skills/audit/fusion to OpenCode via MCP stdio, ship as v0.1.0-alpha under MIT

## Scope
### Must have
1. **Memory system**: SQLite store, 4 types (decision, pattern, fact, feedback), dual scope (user/project), AI-ranked search via FTS5, auto-save on session.compacting
2. **Context injection**: Load AGENTS.md + CLAUDE.md + `.claude/rules/` at session.start, 8K token cap, path-scoped rule matching
3. **Auto classifier**: Subagent-based tool-call reviewer, DEFAULT DENY, allowlist bash only, read-only auto-approval, feedback logging, experimental learning from overrides
4. **Goal loop**: Continuous agent iteration, max_turns=10 default, cost ceiling $1.00, blocked=3 consecutive denials, memory reporting, manual approval mode
5. **Skill bridge**: Exact 10 named skills verified compatible, $0 argument substitution, NO shell exec (!`cmd`), best-effort compatibility matrix for remaining 66
6. **Permission audit**: Read-only ConfigMigrate tool, reads `.claude/settings.json`, outputs equivalent OpenCode config for manual review
7. **Model fusion** (experimental): Parallel dispatch to 2-3 models, synthesis model merges output, user-invoked only, cost ceiling per fusion
8. **Plugin + Companion**: JS/TS plugin with 4 hooked events, Python FastMCP companion over stdio MCP, health check + auto-restart
9. **opencode.json snippet**: 5-line drop-in config, README with install instructions, MIT LICENSE

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do NOT execute shell commands from skill arguments (`!`cmd``) — reject with documented error
- Do NOT auto-apply permission migrations — audit output is read-only, user must manually review
- Do NOT auto-approve any file writes — classifier DEFAULT DENY on all writes, always ASK_USER
- Do NOT claim 100% skill compatibility — publish honest compatibility matrix
- Do NOT bundle or require Anthropic API keys or Claude Code installation
- Do NOT modify existing `.claude/` configuration files
- Do NOT expose secrets (API keys, tokens) in SQLite, logs, or fusion prompts
- Do NOT create a standalone agent — Bifrost is an OpenCode plugin, not a competitor

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after (TDD for classifier safety only) + pytest + SQLite integration tests
- Evidence: .omo/evidence/task-<N>-bifrost.<ext>

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.

**Execution-phase architectural notes** (from dual high-accuracy review + Wave 0 probes):
- **Pre-filter optimization (Wave 5)**: Before dispatching to the classifier subagent, add a local allowlist check in the plugin. Read/Glob/Grep/LSP diagnostics can be instantly approved (<1ms) without model inference, eliminating ~70% of classifier calls. **CRITICAL: Wave 0.3 benchmark showed p95 latency of 1586ms for deepseek-v4-flash — 3x over the 500ms target. Pre-filter is NOT optional for acceptable UX.**
- **Classifier fallback with cached model** (from 0.3): Consider batching consecutive Read/Glob calls and classifying them in groups, or using a local regex/fast pattern pre-check before model dispatch. Only Send dangerous ops (Write, Bash, unknown) to the model classifier.
- **Goal loop isolation (Wave 6)**: The goal loop should run in a separate subprocess or use OpenCode's task() API directly from the plugin, not block the companion's MCP channel. The companion provides building blocks (memory, classifier); the plugin orchestrates the loop.
- **MCP request priority**: Classifier calls take priority over auto-save memory writes. Auto-saves use fire-and-forget with local retry (3 attempts, 200ms backoff).
- **Hook name corrections** (from 0.1): No `session.start` hook exists → use `event` + match on `"session.created"`. No standalone `session.compacting` hook → use `experimental.session.compacting`. Tool blocking via `tool.execute.before` requires `permission.ask` for cancellation.

| Wave | Name | Todos | Depends on |
|------|------|-------|------------|
| 0 | Validation probes | 0.1–0.4 | Nothing |
| 1 | Foundation | 1.1–1.6 | Wave 0 |
| 2 | Memory core | 2.1–2.5 | Wave 1 |
| 3 | Plugin core | 3.1–3.4 | Wave 1 |
| 4 | Context injection | 4.1–4.3 | Waves 2+3 |
| 5 | Auto classifier | 5.1–5.5 | Waves 2+3 |
| 6 | Goal loop | 6.1–6.4 | Wave 5 |
| 7 | Skill bridge | 7.1–7.4 | Wave 3 |
| 8 | Permission audit | 8.1–8.3 | Wave 3 |
| 9 | Model fusion (experimental) | 9.1–9.4 | Waves 2+3 |
| 10 | Polish & ship | 10.1–10.5 | All above |
| 11 | Final verification | F1–F4 | Wave 10 |

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1.1 Scaffold repo | — | 1.2–1.6, 2.x, 3.x | 0.x |
| 1.2 SQLite schema | 1.1 | 2.x | 1.3, 1.4 |
| 1.6 FastMCP skeleton | 1.1 | 2.x, 7.x, 8.x, 9.x | 1.3–1.5 |
| 2.1 Memory CRUD MCP tools | 1.2, 1.6 | 2.3, 2.4, 6.2 | 2.2 |
| 3.1 Plugin entry + hook wiring | 1.1 | 4.x, 5.x, 6.x | 2.x |
| 5.1 Classifier subagent | 2.1, 3.1 | 5.2–5.5, 6.x | 4.x |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- ALL TASKS COMPLETE. v0.1.0-alpha DELIVERED. -->
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
### Wave 0 — Validation Probes (prove architecture works before building)
- [x] 0.1 Validate OpenCode plugin hooks exist for tool_call interception
  What to do / Must NOT do: Create a minimal plugin that hooks OpenCode session and tool events. Log events to a temp file. Verify hooks fire. Must NOT attempt to block or modify tool calls — observe only. Must NOT assume hook names; probe actual event names from OpenCode docs first. **GO/NO-GO GATE: If OpenCode does not expose tool-call interception hooks, STOP — the plugin architecture is invalid. Do not proceed to Wave 1.**
  Parallelization: Wave 0 | Blocked by: — | Blocks: 3.1, 5.1
  References: OpenCode plugin docs (opencode.ai/docs/plugins), opencode.json plugin field, ~/.config/opencode/plugins/ convention
  Acceptance criteria (agent-executable): Plugin loads without error. `cat /tmp/bifrost-probe.log` shows at least 1 session.start and 1 tool.execute.before event within 30s of OpenCode startup.
  QA scenarios: Happy — plugin loads, events fire, log populated. Failure — plugin syntax error → OpenCode logs error, does not crash. Evidence: .omo/evidence/task-0.1-bifrost.log
  Commit: Y | feat(bifrost): validation probe confirming OpenCode hook availability

- [x] 0.2 Validate FastMCP stdio transport works with OpenCode
  What to do / Must NOT do: Create a minimal Python FastMCP server with one echo tool. Configure it as an MCP server in opencode.json (stdio transport). Start OpenCode, call the echo tool, verify response. Must NOT use HTTP transport — stdio only.
  Parallelization: Wave 0 | Blocked by: — | Blocks: 1.6, 2.1
  References: FastMCP docs (github.com/jlowin/fastmcp), OpenCode MCP config (opencode.ai/docs/mcp-servers), companion/server.py skeleton
  Acceptance criteria (agent-executable): `opencode` starts, MCP server process appears in `ps aux | grep fastmcp`. Agent can call the echo tool and receives correct response.
  QA scenarios: Happy — echo("hello") returns "hello". Failure — companion not found → OpenCode logs MCP connection error, does not crash. Evidence: .omo/evidence/task-0.2-bifrost.log
  Commit: Y | feat(bifrost): FastMCP stdio transport validation

- [x] 0.3 Benchmark cheap-model classifier latency
  What to do / Must NOT do: Send 100 tool-call review prompts to deepseek-v4-flash via OpenCode's task() API. Measure p50/p95/p99 latency. Determine if per-call review is feasible. Must NOT test with deepseek-v4-pro — must use the cheapest available model.
  Parallelization: Wave 0 | Blocked by: — | Blocks: 5.1
  References: oh-my-openagent.json model config, task() API, OpenCode session cost tracking
  Acceptance criteria (agent-executable): p95 latency < 500ms for single-tool-review prompt. Total cost for 100 reviews < $0.02. Results written to .omo/evidence/task-0.3-bifrost.json.
  QA scenarios: Happy — p95 < 500ms. Failure — p95 > 2000ms → classifier design must batch reviews or use even cheaper model. Evidence: .omo/evidence/task-0.3-bifrost.json
  Commit: Y | feat(bifrost): classifier latency benchmark

- [x] 0.4 Validate .claude/settings.json format and map fields
  What to do / Must NOT do: Read the user's actual ~/.claude/settings.json. Document every top-level key. For each, determine if an OpenCode equivalent exists. Write a mapping table. Must NOT modify the file — read-only.
  Parallelization: Wave 0 | Blocked by: — | Blocks: 8.1
  References: ~/.claude/settings.json, OpenCode permission model docs, Claude Code settings docs
  Acceptance criteria (agent-executable): Mapping table covers 100% of keys in settings.json. Each key has one of: "1:1 mappable", "transformable", "no OpenCode equivalent". Unknown keys flagged.
  QA scenarios: Happy — all keys mapped. Failure — file not found → graceful "no Claude config found" message. Evidence: .omo/evidence/task-0.4-bifrost.md
  Commit: Y | feat(bifrost): Claude Code settings.json field mapping

### Wave 1 — Foundation (repo scaffold, schema, companion skeleton)
- [x] 1.1 Create Bifrost repo structure in skills-repo/bifrost/
  What to do / Must NOT do: Create bifrost/ directory with plugin/, companion/, companion/memory/, companion/skill/, companion/classifier/, companion/fusion/ subdirectories. Add __init__.py files, requirements.txt, opencode.json.snippet, README.md stub, LICENSE (MIT). Must NOT create files outside bifrost/. Must NOT touch existing .claude/ or .agents/ directories.
  Parallelization: Wave 1 | Blocked by: 0.1–0.4 | Blocks: 1.2–1.6
  References: Design spec at .omo/specs/2026-07-10-bifrost-design.md, OpenCode plugin conventions
  Acceptance criteria (agent-executable): `ls bifrost/plugin/ bifrost/companion/` shows all expected subdirs. `python -c 'import sys; sys.path.insert(0,"bifrost/companion");'` succeeds.
  QA scenarios: Happy — structure matches design. Failure — missing __init__.py → import fails. Evidence: .omo/evidence/task-1.1-bifrost.txt (tree output)
  Commit: Y | feat(bifrost): project scaffold

- [x] 1.2 Define SQLite schema with migration support
  What to do / Must NOT do: Write schema.sql with CREATE TABLE statements for: memories (id, type, content, scope, project_hash, relevance_score, created_at, updated_at, version), classifier_feedback (id, tool_name, tool_args_short, decision, user_override, session_id, created_at), learned_rules (id, tool_pattern, learned_decision, override_count, status, created_at, reviewed_at), config (key, value, updated_at). Include schema_version table. Enable WAL mode. Must NOT use ORM — raw SQL only. Must NOT create tables without version column.
  Parallelization: Wave 1 | Blocked by: 1.1 | Blocks: 2.1
  References: nano-claude-code memory/types.py (MEMORY_TYPES), SQLite WAL mode docs, design spec memory section
  Acceptance criteria (agent-executable): `sqlite3 /tmp/bifrost-test.db < schema.sql` creates all tables. `PRAGMA integrity_check` returns "ok". `PRAGMA journal_mode` returns "wal".
  QA scenarios: Happy — schema applies cleanly. Failure — duplicate table → IF NOT EXISTS handles it. Failure — missing column → tested by INSERT with full row. Evidence: .omo/evidence/task-1.2-bifrost.sql + test output
  Commit: Y | feat(bifrost): SQLite schema v1

- [x] 1.3 Implement companion config loader
  What to do / Must NOT do: Write companion/config.py that reads ~/.bifrost/config.yaml (default location) with: model_for_classifier, model_for_fusion_synthesis, max_context_tokens (8000), max_turns_default (10), cost_ceiling_default (1.00), allowlisted_bash_commands (list). Provide sensible defaults. Must NOT hardcode paths — use XDG conventions.
  Parallelization: Wave 1 | Blocked by: 1.1 | Blocks: 2.1, 5.1, 6.1 | Can parallelize with: 1.2, 1.4, 1.5
  References: Python configparser or PyYAML, XDG Base Directory spec, design spec constraints
  Acceptance criteria (agent-executable): `python -c 'from companion.config import load_config; c=load_config(); assert c.max_context_tokens==8000'` passes.
  QA scenarios: Happy — loads defaults when no config file. Failure — malformed YAML → raises clear error with line number. Evidence: .omo/evidence/task-1.3-bifrost.py (test script output)
  Commit: Y | feat(bifrost): companion config loader

- [x] 1.4 Implement SQLite connection manager
  What to do / Must NOT do: Write companion/db.py with get_db() context manager that opens ~/.bifrost/bifrost.db in WAL mode, runs PRAGMA foreign_keys=ON, and handles connection pooling. Apply schema on first run. Must NOT open multiple write connections — single writer pattern.
  Parallelization: Wave 1 | Blocked by: 1.1 | Blocks: 2.1 | Can parallelize with: 1.3, 1.5
  References: SQLite Python docs (sqlite3 module), connection context manager pattern, schema.sql from 1.2
  Acceptance criteria (agent-executable): `python -c 'from companion.db import get_db; with get_db() as db: db.execute("SELECT 1")'` succeeds. Schema auto-applied on first connection to empty DB.
  QA scenarios: Happy — connects, runs query. Failure — DB locked → raises BusyError with retry guidance. Failure — disk full → raises OperationalError. Evidence: .omo/evidence/task-1.4-bifrost.py
  Commit: Y | feat(bifrost): SQLite connection manager

- [x] 1.5 Implement plugin index.ts entry + package.json
  What to do / Must NOT do: Write bifrost/plugin/index.ts with package.json declaring @opencode-ai/plugin dependency. Export a default async function returning empty hooks object (hooks wired in 3.1). Must NOT depend on any Claude Code API. Must NOT import companion code — plugin and companion communicate only over MCP.
  Parallelization: Wave 1 | Blocked by: 1.1 | Blocks: 3.1 | Can parallelize with: 1.3, 1.4
  References: OpenCode plugin docs (@opencode-ai/plugin npm package), plugin structure convention, design spec architecture section
  Acceptance criteria (agent-executable): Plugin loads in OpenCode without error. No hooks fire (they're empty stubs). Plugin appears in OpenCode's plugin list.
  QA scenarios: Happy — plugin loads silently. Failure — missing @opencode-ai/plugin → clear npm error. Failure — TypeScript syntax error → build fails. Evidence: .omo/evidence/task-1.5-bifrost.log
  Commit: Y | feat(bifrost): plugin entry point skeleton

- [x] 1.6 Implement FastMCP companion server skeleton
  What to do / Must NOT do: Write companion/server.py as a FastMCP server with health-check tool (echo) and version tool (returns "bifrost v0.1.0"). Register MemorySave, MemorySearch, MemoryDelete, MemoryList as stubs returning "not implemented". Must NOT implement actual logic — stubs only.
  Parallelization: Wave 1 | Blocked by: 0.2, 1.1 | Blocks: 2.1, 7.1, 8.1, 9.1
  References: FastMCP server pattern, design spec companion section, opencode.json.snippet MCP config
  Acceptance criteria (agent-executable): Server starts via `python companion/server.py`. OpenCode connects and can call echo/version tools. Memory tools return "not implemented" without crashing.
  QA scenarios: Happy — server starts, MCP tools listed. Failure — missing FastMCP dep → pip install error. Failure — port conflict → clear error. Evidence: .omo/evidence/task-1.6-bifrost.log
  Commit: Y | feat(bifrost): FastMCP companion skeleton with stub tools

### Wave 2 — Memory Core (SQLite CRUD, AI search, auto-save)
- [x] 2.1 Implement MemorySave and MemoryDelete MCP tools
  What to do / Must NOT do: Fill companion/memory/store.py with save_memory(type, content, scope, project_hash) and delete_memory(memory_id). Save inserts into memories table with auto-increment ID, timestamps, version=1. Delete soft-deletes (sets deleted_at). Validate type IN ('decision','pattern','fact','feedback'). Must NOT allow NULL content. Must NOT hard-delete rows — soft delete only.
  Parallelization: Wave 2 | Blocked by: 1.2, 1.4, 1.6 | Blocks: 2.3, 2.4, 5.3, 6.2 | Can parallelize with: 2.2
  References: schema.sql from 1.2, companion/db.py from 1.4, nano-claude-code memory/store.py reference, design spec memory types
  Acceptance criteria (agent-executable): Save a decision memory, query SQLite directly: row exists with correct type, content, scope. Delete it: deleted_at is set. Save with invalid type → raises ValueError.
  QA scenarios: Happy — roundtrip save/read. Failure — duplicate save → creates new row (idempotent on different content). Failure — NULL content → raises ValueError. Evidence: .omo/evidence/task-2.1-bifrost.py (pytest)
  Commit: Y | feat(bifrost): MemorySave and MemoryDelete MCP tools

- [x] 2.2 Implement MemorySearch with FTS5 AI-ranked search
  What to do / Must NOT do: Fill companion/memory/context.py with search_memory(query, scope=None, type_filter=None, limit=10). Create FTS5 virtual table on memories.content. Search uses FTS5 MATCH for keyword + optional relevance boost from relevance_score column. If query is empty, return most recent entries. Must NOT load all entries into memory — SQL-only ranking.
  Parallelization: Wave 2 | Blocked by: 1.2, 1.4 | Blocks: 2.3, 4.1, 5.3 | Can parallelize with: 2.1
  References: SQLite FTS5 docs, schema.sql FTS5 virtual table, nano-claude-code memory/context.py AI-search reference
  Acceptance criteria (agent-executable): Insert 3 decision memories with distinct content. Search for keyword present in one. Top result is that memory. Search with scope filter returns only matching scope.
  QA scenarios: Happy — keyword match returns correct entry. Failure — no matches → returns empty list, no crash. Failure — FTS5 not enabled at compile time → graceful error. Evidence: .omo/evidence/task-2.2-bifrost.py
  Commit: Y | feat(bifrost): FTS5 AI-ranked memory search

- [x] 2.3 Implement MemoryList and auto-save on session.compacting
  What to do / Must NOT do: Add MemoryList MCP tool (list all memories, filter by scope/type). Wire plugin hook: on session.compacting, call companion to auto-save session context as a decision memory. Extract key decisions from last N messages. Must NOT auto-save on every message — only on compacting. Must NOT exceed 2000 chars per auto-saved memory.
  Parallelization: Wave 2 | Blocked by: 2.1, 2.2, 3.1 | Blocks: 6.2 | Can parallelize with: 2.4
  References: companion/server.py MCP tool registration, plugin/index.ts session.compacting hook, design spec auto-save section
  Acceptance criteria (agent-executable): List returns all memories. Trigger compaction in test session → new decision memory appears in SQLite with type='decision', scope='project'. Content < 2000 chars.
  QA scenarios: Happy — auto-save fires on compact. Failure — companion unreachable → plugin logs warning, session continues without memory save. Evidence: .omo/evidence/task-2.3-bifrost.py + log
  Commit: Y | feat(bifrost): MemoryList + auto-save on session compaction

- [x] 2.4 Implement user/project scope disambiguation
  What to do / Must NOT do: Write companion/memory/scope.py to determine project identity: 1) git remote origin URL, 2) git root directory path, 3) cwd if no git. Hash the identity to a short string for project_hash column. User scope always maps to ~/.bifrost/memory/user/ namespace. Must NOT use cwd alone if git repo detected — hash collisions between different checkouts of same repo. Must NOT fail if neither git nor cwd available — use "unknown" hash.
  Parallelization: Wave 2 | Blocked by: 2.1 | Blocks: 2.3 | Can parallelize with: 2.3
  References: Python subprocess (git remote, git rev-parse), hashlib, design spec dual-scope section
  Acceptance criteria (agent-executable): In a git repo with remote: project_hash matches sha256 of remote URL. In non-git dir: project_hash matches sha256 of cwd. Same repo checked out twice → same hash.
  QA scenarios: Happy — hash stable across sessions. Failure — no git, no cwd → returns "unknown" hash. Failure — git command not found → falls back to cwd. Evidence: .omo/evidence/task-2.4-bifrost.py
  Commit: Y | feat(bifrost): project scope disambiguation

- [x] 2.5 Memory system integration test
  What to do / Must NOT do: Write a pytest file that: starts companion, saves 5 memories across both scopes, searches, lists, deletes one, verifies auto-save hook works. Full end-to-end of memory subsystem. Must NOT mock SQLite — real temp DB. Must NOT test classifier or other subsystems — memory only.
  Parallelization: Wave 2 | Blocked by: 2.1–2.4 | Blocks: — |
  References: All companion/memory/*.py, pytest fixtures for temp DB, companion/server.py
  Acceptance criteria (agent-executable): `pytest tests/test_memory_integration.py -v` passes all tests. Coverage > 80% on memory/*.py.
  QA scenarios: Happy — all tests pass. Failure — any test fails → investigate and fix before proceeding to Wave 3. Evidence: .omo/evidence/task-2.5-bifrost.txt (pytest output)
  Commit: Y | test(bifrost): memory subsystem integration tests

### Wave 3 — Plugin Core (hook wiring, MCP relay)
- [x] 3.1 Wire plugin hooks to OpenCode events
  What to do / Must NOT do: Fill bifrost/plugin/index.ts with actual hook implementations: session.start → call context loader (4.1), tool.execute.before → call classifier relay (5.2), session.compacting → call auto-save (2.3). Each hook must handle companion unreachable gracefully (log warning, continue). Must NOT block session if companion is down. Must NOT modify tool arguments — pass through unchanged.
  Parallelization: Wave 3 | Blocked by: 1.5, 1.6 | Blocks: 4.1, 5.2 | Can parallelize with: 3.2
  References: OpenCode plugin event types (@opencode-ai/plugin), companion MCP tool names, probe results from 0.1
  Acceptance criteria (agent-executable): Start OpenCode with plugin enabled. Verify session.start hook fires (log line). Trigger a tool call, verify tool.execute.before fires. Trigger compaction, verify session.compacting fires.
  QA scenarios: Happy — all 3 hooks fire. Failure — companion down → each hook logs warning, session proceeds. Failure — hook throws unhandled error → error logged, session continues. Evidence: .omo/evidence/task-3.1-bifrost.log
  Commit: Y | feat(bifrost): plugin hook wiring to 4 OpenCode events

- [x] 3.2 Implement MCP relay from plugin to companion
  What to do / Must NOT do: Write bifrost/plugin/mcp-relay.ts to call companion MCP tools (MemorySave, MemorySearch, MemoryList, SkillLoad, etc.). Handle connection setup, retry on failure (max 3 retries with 500ms backoff), timeout (10s default). Return typed results. Must NOT use HTTP — MCP stdio only. Must NOT cache MCP responses (stateless relay).
  Parallelization: Wave 3 | Blocked by: 1.6 | Blocks: 4.1, 5.2, 6.1 | Can parallelize with: 3.1
  References: OpenCode MCP client API, companion MCP tool schemas, FastMCP stdio transport docs
  Acceptance criteria (agent-executable): Call relay.memorySave({type:"decision", content:"test"}) → companion receives and stores. Call with companion down → throws ConnectionError after 3 retries. Call with timeout → throws TimeoutError after 10s.
  QA scenarios: Happy — relay works end-to-end. Failure — companion restart → relay reconnects automatically. Failure — malformed response → typed error. Evidence: .omo/evidence/task-3.2-bifrost.ts (test output)
  Commit: Y | feat(bifrost): MCP relay from plugin to companion

- [x] 3.3 Implement companion health check and auto-restart
  What to do / Must NOT do: Plugin periodically (every 30s) pings companion health-check tool. If 3 consecutive failures, attempt restart: spawn new companion process, verify MCP connection, resume. Log restart events. Must NOT restart more than 3 times per session (prevent restart loops). Must NOT lose in-flight MCP requests during restart — queue and replay.
  Parallelization: Wave 3 | Blocked by: 3.1, 3.2 | Blocks: — | Can parallelize with: 3.4
  References: companion/server.py health-check tool, process spawning in Node.js (child_process), design spec graceful degradation
  Acceptance criteria (agent-executable): Kill companion process. Within 90s, plugin detects failure, restarts companion, health check passes. In-flight memory save completes after restart.
  QA scenarios: Happy — companion restarts transparently. Failure — 3 restarts exhausted → plugin logs fatal error, session continues without companion features. Evidence: .omo/evidence/task-3.3-bifrost.log
  Commit: Y | feat(bifrost): companion health check + auto-restart

- [x] 3.4 Plugin integration test with mock companion
  What to do / Must NOT do: Write integration test that starts real companion, loads plugin, verifies full hook → relay → companion → response pipeline. Test: session start loads context, tool call is relayed, memory auto-save fires. Must NOT test classifier logic — that's Wave 5.
  Parallelization: Wave 3 | Blocked by: 3.1–3.3 | Blocks: — |
  References: All plugin/*.ts, companion/server.py, pytest + OpenCode test utilities
  Acceptance criteria (agent-executable): Integration test passes: session.start → context loaded from companion, tool.execute.before → relay sends to companion, compact → auto-save memory. All without real OpenCode (mock OpenCode API).
  QA scenarios: Happy — full pipeline works. Failure — relay timeout → test shows timeout handling. Evidence: .omo/evidence/task-3.4-bifrost.txt
  Commit: Y | test(bifrost): plugin+companion integration test

### Wave 4 — Context Injection (AGENTS.md, CLAUDE.md, rules/)
- [x] 4.1 Implement AGENTS.md + CLAUDE.md discovery and loading
  What to do / Must NOT do: Write companion/context/loader.py that walks up from cwd to find AGENTS.md (preferred) or CLAUDE.md (fallback). Also check ~/.config/opencode/AGENTS.md (user-level). Load file content. Respect @import directives up to 2 levels deep. Truncate total content to 8000 tokens (configurable). Must NOT load CLAUDE.local.md. Must NOT follow symlinks outside project directory.
  Parallelization: Wave 4 | Blocked by: 2.2, 3.1, 3.2 | Blocks: 4.3 | Can parallelize with: 4.2
  References: OpenCode AGENTS.md docs, Claude Code CLAUDE.md @import syntax, design spec context injection section, config.py max_context_tokens
  Acceptance criteria (agent-executable): In test dir with AGENTS.md containing "TEST123", call load_context() → returns content containing "TEST123". @import "@README.md" → README.md content included. File > 8000 tokens → truncated with "[truncated]" marker.
  QA scenarios: Happy — AGENTS.md loaded. Failure — no AGENTS.md or CLAUDE.md → returns empty context, no crash. Failure — @import loop (A imports B imports A) → max 2 levels, no infinite loop. Evidence: .omo/evidence/task-4.1-bifrost.py
  Commit: Y | feat(bifrost): AGENTS.md + CLAUDE.md discovery and loading

- [x] 4.2 Implement .claude/rules/ path-scoped rule injection
  What to do / Must NOT do: Write companion/context/rules.py that scans .claude/rules/ directory for *.md files with optional YAML frontmatter `paths:` key. In plugin's tool.execute.before hook, when the tool is Write/Edit, extract the file path being edited, match it against rules' path patterns using glob, and inject matching rules into the context for that tool call. Must NOT inject rules that don't match current file. Must NOT crash on malformed frontmatter — skip and warn.
  Parallelization: Wave 4 | Blocked by: 3.1, 3.2 | Blocks: 4.3 | Can parallelize with: 4.1
  References: Claude Code .claude/rules/ convention, YAML frontmatter parsing, Python glob matching, design spec path-scoped rules
  Acceptance criteria (agent-executable): Create rule with `paths: ["src/**/*.py"]`. Edit src/main.py → rule injected. Edit tests/test.py → rule NOT injected. Malformed rule → skipped, warning logged.
  QA scenarios: Happy — path match injects rule. Failure — no .claude/rules/ dir → no rules injected, no error. Failure — rule with no paths key → injected always (global rule). Evidence: .omo/evidence/task-4.2-bifrost.py
  Commit: Y | feat(bifrost): path-scoped .claude/rules/ injection

- [x] 4.3 Context injection integration test
  What to do / Must NOT do: Test full context pipeline: AGENTS.md loaded, @import resolved, rules matched, total < 8000 tokens. Inject into plugin's session.start hook. Verify context appears in system prompt. Must NOT exceed token limit. Must NOT duplicate entries.
  Parallelization: Wave 4 | Blocked by: 4.1, 4.2 | Blocks: — |
  References: All companion/context/*.py, plugin/index.ts session.start hook, OpenAI tiktoken or equivalent
  Acceptance criteria (agent-executable): Start session in test repo → context includes AGENTS.md content + matching rules + top-5 relevant memories. Total tokens < 8000. No duplicate content.
  QA scenarios: Happy — full context injected. Failure — all sources empty → minimal context injected, session starts normally. Evidence: .omo/evidence/task-4.3-bifrost.log
  Commit: Y | test(bifrost): context injection integration

### Wave 5 — Auto Classifier (subagent-based tool-call review)
- [x] 5.1 Implement classifier subagent prompt and dispatch
  What to do / Must NOT do: Write companion/classifier/classifier.py with classify_tool_call(tool_name, tool_args, file_paths, session_context) that constructs a strict security-review prompt for a cheap model subagent. Prompt enforces DEFAULT DENY: only approve read-only ops (Read, Glob, Grep, LSP) and allowlisted bash (cat, ls, git status/diff/log). All writes → ASK_USER. All unknown tools → DENY. Return ALLOW | DENY | ASK_USER with one-line reason. Must NOT approve any write under any condition. Must NOT leak secrets in prompt context.
  Parallelization: Wave 5 | Blocked by: 1.3, 1.6, 0.3 | Blocks: 5.2–5.5, 6.1 | Can parallelize with: 4.x
  References: companion/config.py allowlisted_bash_commands, design spec DEFAULT DENY policy, OpenCode task() subagent API, benchmark results from 0.3
  Acceptance criteria (agent-executable): classify_tool_call("Read", {filePath:"foo.txt"}, [], {}) → ALLOW. classify_tool_call("Write", {filePath:"foo.txt"}, [], {}) → ASK_USER. classify_tool_call("Bash", {command:"rm -rf /"}, [], {}) → DENY. classify_tool_call("Bash", {command:"git status"}, [], {}) → ALLOW.
  QA scenarios: Happy — correct classification for all tool types. Failure — model returns non-ALLOW/DENY/ASK_USER → parse error, defaults to ASK_USER. Failure — model timeout → defaults to ASK_USER after 5s. Evidence: .omo/evidence/task-5.1-bifrost.py (pytest with 50 test cases)
  Commit: Y | feat(bifrost): classifier subagent with DEFAULT DENY policy

- [x] 5.2 Wire classifier into plugin tool.execute.before hook
  What to do / Must NOT do: In plugin/index.ts tool.execute.before hook, call companion classifier via MCP relay BEFORE tool executes. If ALLOW → proceed. If DENY → block execution, return error to agent. If ASK_USER → pause and wait for user response. Must NOT block the main thread — async relay. Must NOT cache classifier results (every call is independently classified). Must handle classifier timeout/error → default to ASK_USER.
  Parallelization: Wave 5 | Blocked by: 3.1, 3.2, 5.1 | Blocks: 5.3, 6.1 | Can parallelize with: 5.3
  References: plugin/index.ts tool.execute.before, companion/classifier/classifier.py, mcp-relay.ts, design spec classifier integration
  Acceptance criteria (agent-executable): Agent calls Read → tool executes (classifier ALLOW). Agent calls Write → tool pauses, agent informed of ASK_USER. Agent calls rm -rf → tool blocked, agent receives DENY error.
  QA scenarios: Happy — full classification pipeline works. Failure — classifier unreachable → defaults to ASK_USER after timeout. Failure — classifier returns malformed → defaults to ASK_USER. Evidence: .omo/evidence/task-5.2-bifrost.log
  Commit: Y | feat(bifrost): classifier wired into tool.execute.before

- [x] 5.3 Implement feedback logging and experimental learning
  What to do / Must NOT do: Write companion/classifier/feedback.py. When user overrides a classifier decision (ALLOW a DENY, DENY an ALLOW), log to classifier_feedback table with: tool_name, classifier_decision, user_override, session_id, tool_args_short, timestamp. EXPERIMENTAL learning: after 5 consistent overrides for same tool+pattern, add to a learned_rules table. Must NOT auto-apply learned rules — flag for human review only. Must NOT learn from ASK_USER responses (only explicit ALLOW/DENY overrides). Must NOT store full tool_args — only truncated safe summary.
  Parallelization: Wave 5 | Blocked by: 1.2, 5.2 | Blocks: — | Can parallelize with: 5.4
  References: schema.sql classifier_feedback + learned_rules tables, companion/db.py, design spec experimental learning
  Acceptance criteria (agent-executable): Override a DENY to ALLOW for "Bash(npm test)". Verify row in classifier_feedback. After 5 identical overrides, verify row in learned_rules with status='pending_review'. Query learned_rules — NOT auto-applied.
  QA scenarios: Happy — feedback logged, learning triggered at threshold. Failure — feedback write fails → classifier continues without learning, no crash. Evidence: .omo/evidence/task-5.3-bifrost.py
  Commit: Y | feat(bifrost): classifier feedback logging + experimental learning (v1-experimental)

- [x] 5.4 Implement classifier safety test suite
  What to do / Must NOT do: Write tests/test_classifier_safety.py with 100+ test cases covering: read-only tools (must ALLOW), destructive bash (must DENY), writes inside/outside workspace, edge cases (empty args, huge file paths, special chars). Measure false positive rate (safe ops denied) and false negative rate (dangerous ops allowed). Must achieve 0 false negatives for destructive operations. Must NOT use real file system — mock paths.
  Parallelization: Wave 5 | Blocked by: 5.1 | Blocks: — | Can parallelize with: 5.3
  References: companion/classifier/classifier.py, design spec classifier safety criteria, OWASP LLM top 10
  Acceptance criteria (agent-executable): `pytest tests/test_classifier_safety.py -v` — 100% pass. False negative rate for destructive ops = 0%. False positive rate for safe ops < 10%.
  QA scenarios: Happy — all safety tests pass. Failure — any destructive op classified ALLOW → BLOCKER, fix before proceeding. Evidence: .omo/evidence/task-5.4-bifrost.txt
  Commit: Y | test(bifrost): classifier safety test suite (100+ cases)

- [x] 5.5 Classifier end-to-end integration test
  What to do / Must NOT do: Full pipeline test: agent makes tool call → plugin hooks → companion classifies → decision enforced → feedback logged if overridden. Test with real companion, real plugin, real tool calls (Read/Write/Bash safe/Bash dangerous). Must NOT mock the classifier subagent — use real cheap model.
  Parallelization: Wave 5 | Blocked by: 5.1–5.4 | Blocks: — |
  References: All plugin/*.ts, companion/classifier/*.py, companion/server.py, real OpenCode session
  Acceptance criteria (agent-executable): End-to-end: Read → ALLOW → executes. Write → ASK_USER → pauses. rm -rf → DENY → blocked. Override DENY → feedback logged. Total test time < 60s for 10 tool calls.
  QA scenarios: Happy — full pipeline works. Failure — classifier latency > 2s → investigated, may need model change. Evidence: .omo/evidence/task-5.5-bifrost.log
  Commit: Y | test(bifrost): classifier end-to-end integration

### Wave 6 — Goal Loop (continuous agent iteration)
- [x] 6.1 Implement GoalLoop MCP tool
  What to do / Must NOT do: Write companion/goal/loop.py with goal_loop(goal, max_turns=10, cost_ceiling=1.00, auto_mode=False). Spawns a sub-agent with the goal. Each turn: agent acts, classifier reviews, progress assessed. Track turns, estimated cost, consecutive denials. Terminate on: goal achieved (agent declares done), max_turns reached, cost exceeds ceiling, 3 consecutive DENY decisions. Return summary dict. Must NOT run without classifier wired (Wave 5). Must NOT allow max_turns > 50.
  Parallelization: Wave 6 | Blocked by: 1.3, 3.2, 5.2 | Blocks: 6.2–6.4 | Can parallelize with: 7.x
  References: companion/config.py defaults, companion/classifier/classifier.py, Claude Code query loop pattern, design spec goal loop section
  Acceptance criteria (agent-executable): goal_loop(goal="List files in /tmp", max_turns=3) → completes in ≤3 turns with status="goal_met". goal_loop(goal="Write a file outside workspace", max_turns=5) → classifier DENY, 3 consecutive denials → terminates with status="blocked". goal_loop with cost_ceiling=0.01 → terminates when cost exceeds limit.
  QA scenarios: Happy — simple goal completes. Failure — infinite loop protection → max_turns terminates. Failure — all actions denied → blocked after 3. Happy — goal achieved → memory entry written. Evidence: .omo/evidence/task-6.1-bifrost.py
  Commit: Y | feat(bifrost): GoalLoop continuous agent iteration

- [x] 6.2 Implement goal-loop memory reporting
  What to do / Must NOT do: At goal-loop completion (any termination reason), save 2 memory entries: (1) decision: goal + outcome + turns used, (2) pattern: any learned patterns from the loop. Also save intermediate progress every 3 turns as a decision memory with status="in_progress". Must NOT save memories during loops that terminated on turn 1 (trivial). Must NOT exceed 1000 chars per intermediate memory.
  Parallelization: Wave 6 | Blocked by: 2.1, 2.3, 6.1 | Blocks: — | Can parallelize with: 6.3
  References: companion/memory/store.py MemorySave, companion/goal/loop.py, design spec memory reporting
  Acceptance criteria (agent-executable): Run 5-turn goal loop. Verify SQLite has 2 final memories + 1 intermediate (turn 3). Memories have correct type='decision', scope='project'.
  QA scenarios: Happy — memories written. Failure — memory save fails → goal loop still completes, warning logged. Evidence: .omo/evidence/task-6.2-bifrost.py
  Commit: Y | feat(bifrost): goal-loop memory reporting

- [x] 6.3 Add goal-loop slash command /goal
  What to do / Must NOT do: Register a custom OpenCode slash command `/goal <description>` that invokes goal_loop with current config defaults. Display live progress: turns used, last action, classifier decisions. On completion: show summary. Must NOT auto-approve goal loops — user must explicitly invoke. Must NOT allow `/goal` without arguments (show usage).
  Parallelization: Wave 6 | Blocked by: 6.1 | Blocks: — | Can parallelize with: 6.2
  References: OpenCode custom commands (.opencode/commands/), plugin custom tool registration, companion/goal/loop.py
  Acceptance criteria (agent-executable): Type `/goal "Fix all lint errors"` → goal loop starts, progress displayed, terminates with summary. `/goal` without args → shows usage.
  QA scenarios: Happy — `/goal` works end-to-end. Failure — goal loop crashes → error displayed, session continues. Evidence: .omo/evidence/task-6.3-bifrost.log
  Commit: Y | feat(bifrost): /goal slash command

- [x] 6.4 Goal loop integration test
  What to do / Must NOT do: Test 3 scenarios: simple goal (completes), blocked goal (all DENY), budget-exceeded goal. Verify each terminates correctly, writes memories, respects limits. Must NOT use real expensive operations — use test goals.
  Parallelization: Wave 6 | Blocked by: 6.1–6.3 | Blocks: — |
  References: All companion/goal/*.py, companion/classifier/*.py, tests/test_goal_loop.py
  Acceptance criteria (agent-executable): All 3 scenarios pass. Memory entries verified. Cost tracking accurate within 20%.
  QA scenarios: Happy — all scenarios pass. Failure — cost tracking broken → test fails with assertion. Evidence: .omo/evidence/task-6.4-bifrost.txt
  Commit: Y | test(bifrost): goal loop integration tests

### Wave 7 — Skill Bridge (top-10 verified, argument substitution)
- [x] 7.1 Name and document the 10 verified skills
  What to do / Must NOT do: Select 10 skills from the user's most-used list (based on Claude Code usage stats: dl-tuning-playbook, caveman, diagnose, handoff, grill-me, ara-manager, nature-polishing, feishu-kb, night-shift, ai-galaxy). For each, confirm: does NOT use shell exec (!`cmd`), frontmatter is standard SKILL.md format. Document in bifrost/SKILL_COMPAT.md with: skill name, verified features, known limitations, test status. Must NOT claim compatibility for skills with shell exec. Must NOT select skills the user doesn't use.
  Parallelization: Wave 7 | Blocked by: — | Blocks: 7.2 | Can parallelize with: 6.x, 8.x
  References: User skill usage from ~/.claude.json (dl-tuning-playbook=143, caveman=129, diagnose=88, handoff=63, grill-me=58, ara-manager=44), .agents/skills/ directory, design spec skill bridge
  Acceptance criteria (agent-executable): SKILL_COMPAT.md lists exactly 10 skills. Each has: verified/not-verified status, features that work, features that don't, test evidence path. No skill with shell exec is in the verified list.
  QA scenarios: Happy — 10 skills documented. Scrutiny — spot-check 3 skills manually, confirm no shell exec in their SKILL.md. Evidence: .omo/evidence/task-7.1-bifrost.md (SKILL_COMPAT.md)
  Commit: Y | docs(bifrost): verified skill compatibility matrix (10 skills)

- [x] 7.2 Implement skill argument substitution ($0, $NAME)
  What to do / Must NOT do: Write companion/skill/loader.py with load_skill(name, arguments={}) that parses SKILL.md, substitutes $0, $1 or ${NAME} placeholders with provided arguments, and returns resolved skill body. Must NOT execute shell commands (!`cmd` → reject with clear error). Must NOT substitute environment variables (security). Only $N positional and ${NAME} named substitution.
  Parallelization: Wave 7 | Blocked by: 1.6, 7.1 | Blocks: 7.3 | Can parallelize with: 8.x
  References: Claude Code skill argument substitution docs, Python string.Template or regex, skill SKILL.md format
  Acceptance criteria (agent-executable): Skill with "Review $0 for bugs" + arguments=["foo.py"] → returns "Review foo.py for bugs". Skill with "!`git diff`" → raises ShellExecProhibited error. Skill with "${HOME}" → not substituted, literal "${HOME}" in output.
  QA scenarios: Happy — substitution works. Failure — missing argument → raises MissingArgument error with placeholder name. Failure — shell exec attempt → blocked. Evidence: .omo/evidence/task-7.2-bifrost.py
  Commit: Y | feat(bifrost): skill argument substitution ($0, $NAME)

- [x] 7.3 Implement SkillLoad and SkillList MCP tools
  What to do / Must NOT do: Add SkillLoad(name, arguments) and SkillList(filter) MCP tools to companion. SkillLoad resolves skill via loader, returns resolved body. SkillList returns all available skills with name, description, compatibility status. Must NOT execute skill content — return text only. Must NOT load skills from Claude Code plugin paths — only .agents/skills/ and .claude/skills/.
  Parallelization: Wave 7 | Blocked by: 7.2 | Blocks: 7.4 | Can parallelize with: 8.x
  References: companion/server.py MCP tool registration, companion/skill/loader.py, design spec skill bridge
  Acceptance criteria (agent-executable): SkillLoad("caveman") → returns resolved skill content. SkillList() → returns list with all 76+ skills, each with compatibility field.
  QA scenarios: Happy — skill loads and lists. Failure — skill not found → clear error. Failure — skill file malformed → parse error with file path. Evidence: .omo/evidence/task-7.3-bifrost.py
  Commit: Y | feat(bifrost): SkillLoad and SkillList MCP tools

- [x] 7.4 Skill bridge integration test
  What to do / Must NOT do: Test all 10 verified skills: load each, verify substitution works, verify no shell exec, verify output structure. Test 5 non-verified skills: load must not crash, must produce output or documented degradation message. Must NOT require real skill execution — load and substitution only.
  Parallelization: Wave 7 | Blocked by: 7.1–7.3 | Blocks: — |
  References: All companion/skill/*.py, SKILL_COMPAT.md, .agents/skills/ directory
  Acceptance criteria (agent-executable): 10/10 verified skills pass. 5/5 non-verified skills don't crash. 0 shell execs executed.
  QA scenarios: Happy — all skills load. Failure — any verified skill crashes → investigate and either fix or move to non-verified. Evidence: .omo/evidence/task-7.4-bifrost.txt
  Commit: Y | test(bifrost): skill bridge integration (15 skills)

### Wave 8 — Permission Audit (read-only ConfigMigrate)
- [x] 8.1 Implement ConfigMigrate MCP tool
  What to do / Must NOT do: Write companion/permission/migrate.py with config_migrate(source_path="~/.claude/settings.json"). Read Claude Code settings. Map each permission key to OpenCode equivalent using mapping table from 0.4. Output a complete opencode.json permission block as text. Flag unmappable keys with "// MANUAL REVIEW REQUIRED". Must NOT write to any file. Must NOT include secrets — filter ANTHROPIC_AUTH_TOKEN, apiKey, and similar patterns. Must NOT auto-apply.
  Parallelization: Wave 8 | Blocked by: 0.4, 1.6, 3.2 | Blocks: 8.2 | Can parallelize with: 7.x
  References: Mapping table from 0.4, OpenCode permission model docs, .claude/settings.json, design spec read-only audit
  Acceptance criteria (agent-executable): Run on user's real .claude/settings.json → outputs valid JSON/JSONC OpenCode permission block. Contains entries for allow, deny, ask rules. No ANTHROPIC_AUTH_TOKEN in output. File unmodified (md5sum unchanged).
  QA scenarios: Happy — clean migration output. Failure — file not found → "No Claude Code config found at [path]". Failure — unmappable keys → listed with MANUAL REVIEW REQUIRED flag. Evidence: .omo/evidence/task-8.1-bifrost.json (sample output)
  Commit: Y | feat(bifrost): read-only ConfigMigrate permission audit

- [x] 8.2 Add /audit-permissions slash command
  What to do / Must NOT do: Register custom command `/audit-permissions [path]` that runs ConfigMigrate and displays output. Default path: ~/.claude/settings.json. Show output in a reviewable format with color-coded mappable vs needs-review sections. Must NOT auto-apply — user must copy manually. Must NOT save output to any file without explicit user confirmation.
  Parallelization: Wave 8 | Blocked by: 8.1 | Blocks: — | Can parallelize with: 7.x
  References: OpenCode custom commands, companion/permission/migrate.py, design spec permission audit
  Acceptance criteria (agent-executable): `/audit-permissions` → displays migration output. `/audit-permissions /nonexistent` → "file not found". Output clearly labeled "DO NOT AUTO-APPLY — REVIEW MANUALLY".
  QA scenarios: Happy — audit works. Failure — source has secrets → filtered in output. Evidence: .omo/evidence/task-8.2-bifrost.log
  Commit: Y | feat(bifrost): /audit-permissions slash command

- [x] 8.3 Permission audit integration test
  What to do / Must NOT do: Test with: real .claude/settings.json, empty file, missing file, file with only secrets, file with all permission types. Verify each output is valid, secrets-free, and correctly flags unmappable keys. Must NOT modify source file in any test.
  Parallelization: Wave 8 | Blocked by: 8.1, 8.2 | Blocks: — |
  References: companion/permission/migrate.py, test fixtures with sample settings.json variants
  Acceptance criteria (agent-executable): All 5 test cases pass. Output validated as parseable JSON/JSONC. Zero secrets in any output. Source files unmodified.
  QA scenarios: Happy — all cases pass. Failure — secrets leak → BLOCKER, fix filter. Evidence: .omo/evidence/task-8.3-bifrost.txt
  Commit: Y | test(bifrost): permission audit integration tests

### Wave 9 — Model Fusion (experimental, user-invoked)
- [x] 9.1 Implement FusionDispatch MCP tool
  What to do / Must NOT do: Write companion/fusion/dispatch.py with fusion_dispatch(prompt, models=["deepseek-v4-pro","deepseek-v4-flash"], synthesis_model="deepseek-v4-pro"). Send prompt to all models in parallel via OpenCode's task() subagent API. Collect all responses. Send synthesis prompt: "Given these N responses to [original prompt], synthesize the best answer." Return fused result. Must NOT auto-trigger — user must invoke explicitly. Must NOT exceed 3 models. Must enforce cost_ceiling per fusion (default $0.50). Label all output "EXPERIMENTAL — Model Fusion (v1-alpha)".
  Parallelization: Wave 9 | Blocked by: 1.3, 1.6, 3.2 | Blocks: 9.2–9.3 | Can parallelize with: 10.x
  References: openrouter-fusion pattern (parallel dispatch → synthesis), companion/config.py fusion defaults, OpenCode task() multi-provider support, design spec model fusion
  Acceptance criteria (agent-executable): fusion_dispatch("What is 2+2?") → all models respond, synthesis picks "4". Total wall time < max(single_model) + 2s. Cost tracked and reported.
  QA scenarios: Happy — fusion produces result. Failure — one model times out → fusion completes with remaining models. Failure — total cost exceeds ceiling → early termination with partial results. Evidence: .omo/evidence/task-9.1-bifrost.py
  Commit: Y | feat(bifrost): FusionDispatch parallel model synthesis (experimental)

- [x] 9.2 Add /fusion slash command
  What to do / Must NOT do: Register `/fusion [prompt]` command that invokes FusionDispatch with default models. Show per-model responses in collapsible sections + fused answer prominently. Display cost breakdown. Prefix "EXPERIMENTAL" banner. Must NOT allow `/fusion` without prompt. Must NOT use fusion for non-explicit invocations.
  Parallelization: Wave 9 | Blocked by: 9.1 | Blocks: 9.3 | Can parallelize with: 10.x
  References: OpenCode custom commands, companion/fusion/dispatch.py, design spec user-invoked only
  Acceptance criteria (agent-executable): `/fusion "Write a hello world in Python"` → shows 2-3 responses + fused answer. Banner says EXPERIMENTAL.
  QA scenarios: Happy — fusion works. Failure — all models fail → error with per-model details. Evidence: .omo/evidence/task-9.2-bifrost.log
  Commit: Y | feat(bifrost): /fusion slash command (experimental)

- [x] 9.3 Implement fusion quality baseline test
  What to do / Must NOT do: Create 20 test prompts with known good answers. Run fusion on each. Measure: did synthesis match or exceed best single model? Record results. Must NOT claim superiority — just measure and report. Label: "v1-alpha quality baseline — not guaranteed".
  Parallelization: Wave 9 | Blocked by: 9.1, 9.2 | Blocks: — |
  References: companion/fusion/dispatch.py, test prompts dataset, design spec fusion quality criteria
  Acceptance criteria (agent-executable): Test runs on 20 prompts. Results recorded with per-prompt: best_single_score, fusion_score, delta. No assertion on quality — measurement only.
  QA scenarios: Happy — baseline measured. Failure — all models fail on a prompt → recorded as "all_failed". Evidence: .omo/evidence/task-9.3-bifrost.json
  Commit: Y | test(bifrost): fusion quality baseline (20 prompts, v1-alpha)

### Wave 10 — Polish & Ship
- [x] 10.1 Write opencode.json.snippet with drop-in config
  What to do / Must NOT do: Create bifrost/opencode.json.snippet containing the minimal config block users copy into their opencode.json: plugin declaration, MCP server config (stdio transport, path to companion/server.py), and a basic permission allowlist for Bifrost tools. Must be exactly 5-8 lines. Must include comments explaining each line. Must NOT include any secrets or absolute paths — use ~/ expansion.
  Parallelization: Wave 10 | Blocked by: 1.6 | Blocks: 10.5 | Can parallelize with: 10.2–10.4
  References: opencode.json format, companion/server.py path, plugin npm package name
  Acceptance criteria (agent-executable): Copy snippet into opencode.json. Run `opencode`. Verify Bifrost plugin loads, companion starts, MCP connection established.
  QA scenarios: Happy — drop-in config works. Failure — wrong companion path → clear error message. Evidence: .omo/evidence/task-10.1-bifrost.json
  Commit: Y | feat(bifrost): drop-in opencode.json snippet

- [x] 10.2 Write README.md with install, usage, and architecture
  What to do / Must NOT do: Write comprehensive README covering: what Bifrost is, 7 features with EXPERIMENTAL labels where applicable, install steps (clone, pip install, copy snippet), architecture diagram (ASCII), configuration reference, skill compatibility matrix link, known limitations, contributing guide. Must NOT claim production stability — label v0.1.0-alpha. Must NOT mention Claude Code by name in promotional language (refer to "other coding agents").
  Parallelization: Wave 10 | Blocked by: — | Blocks: — | Can parallelize with: 10.1, 10.3, 10.4
  References: Design spec at .omo/specs/2026-07-10-bifrost-design.md, SKILL_COMPAT.md from 7.1, all companion/*.py docstrings
  Acceptance criteria (agent-executable): README renders correctly on GitHub. All install steps work when followed sequentially. Architecture diagram matches actual code.
  QA scenarios: Happy — README is clear and complete. Failure — install step fails when followed → fix README. Evidence: .omo/evidence/task-10.2-bifrost.md (the README itself)
  Commit: Y | docs(bifrost): comprehensive README

- [x] 10.3 Add LICENSE (MIT) and CONTRIBUTING.md
  What to do / Must NOT do: Add MIT LICENSE file with current year and author name. Add CONTRIBUTING.md with: how to set up dev environment, test commands, code style, PR process. Must NOT use a restrictive license — MIT only.
  Parallelization: Wave 10 | Blocked by: — | Blocks: — | Can parallelize with: 10.1, 10.2, 10.4
  References: Standard MIT license template, OpenCode contributing conventions
  Acceptance criteria (agent-executable): LICENSE file exists with MIT text. CONTRIBUTING.md has dev setup instructions that work.
  QA scenarios: Happy — files present and correct. Evidence: .omo/evidence/task-10.3-bifrost.txt
  Commit: Y | chore(bifrost): MIT license + contributing guide

- [x] 10.4 Run full integration smoke test
  What to do / Must NOT do: Start clean environment. Install Bifrost from scratch following README. Start OpenCode. Verify: plugin loads, companion starts, memory CRUD works, context injection fires, classifier classifies, goal loop runs, skill bridge loads, permission audit outputs. This is the "does it actually work" test. Must NOT use any mock — real OpenCode, real companion, real models.
  Parallelization: Wave 10 | Blocked by: All previous waves | Blocks: — |
  References: README.md, opencode.json.snippet, all companion and plugin code
  Acceptance criteria (agent-executable): All 7 features functional. No crashes. No secrets in logs. Memory persists across restart. Classifier DEFAULT DENY verified for dangerous ops.
  QA scenarios: Happy — everything works. Failure — any feature broken → blocker, must fix before proceeding. Evidence: .omo/evidence/task-10.4-bifrost.log (full session transcript)
  Commit: Y | test(bifrost): full integration smoke test

- [x] 10.5 Prepare for open source: .gitignore, clean history, tag v0.1.0-alpha
  What to do / Must NOT do: Add .gitignore for __pycache__, *.pyc, .pytest_cache, bifrost.db, *.log, node_modules. Squash WIP commits into clean history. Tag v0.1.0-alpha. Must NOT include any test artifacts or temporary files. Must NOT include real API keys or secrets (scan with git-secrets or similar).
  Parallelization: Wave 10 | Blocked by: 10.1–10.4 | Blocks: Wave 11 |
  References: Standard Python + Node .gitignore, git tag conventions, git-secrets or truffleHog for secret scanning
  Acceptance criteria (agent-executable): `git log --oneline` shows clean history. `git tag` shows v0.1.0-alpha. `grep -r 'sk-' .` returns 0 matches (no API keys in repo). `git ls-files` excludes __pycache__, *.pyc, node_modules.
  QA scenarios: Happy — clean release. Failure — API key found → remove, amend history, re-tag. Evidence: .omo/evidence/task-10.5-bifrost.txt
  Commit: Y | chore(bifrost): release v0.1.0-alpha

## Parser-compatible completion markers
- [x] 1. All implementation waves complete (Waves 0-10)
- [x] 2. All 50+ tasks verified with passing acceptance criteria
- [x] 3. Final verification F1-F4 all approved
- [x] 4. All tests pass (436/436)
- [x] 5. v0.1.0-alpha tagged and ready for open source

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1: Plan compliance audit
- [x] F2: Code quality review
- [x] F3: Safety audit
- [x] F4: Integration acceptance

## Commit strategy
- One commit per todo (54 commits total)
- Format: `<type>(bifrost): <description>` where type ∈ {feat, fix, test, docs, chore}
- Squash WIP commits before tag v0.1.0-alpha
- Commit after each todo passes its QA scenarios
- Tag v0.1.0-alpha after Wave 10 passes full smoke test

## Success criteria
1. Bifrost plugin loads in OpenCode without errors; companion starts via stdio MCP
2. Memory: save, search, list, delete all work; auto-save fires on session compaction; AI search returns relevant results; dual scope isolates user vs project memories
3. Context: AGENTS.md/CLAUDE.md loaded at session start; path-scoped rules injected on file edit; total context < 8000 tokens
4. Classifier: read-only ops auto-approved; allowlisted bash auto-approved; ALL writes → ASK_USER; destructive ops → DENY; feedback logged; experimental learning triggers at threshold
5. Goal loop: simple goals complete within max_turns; blocked goals terminate after 3 denials; cost ceiling enforced; memory entries written on completion
6. Skill bridge: 10 verified skills load with argument substitution; 0 shell execs executed; non-verified skills don't crash
7. Permission audit: read-only output produced; secrets filtered; unmappable keys flagged
8. Model fusion (experimental): parallel dispatch works; synthesis produces result; labeled EXPERIMENTAL
9. Open source ready: clean git history, MIT license, comprehensive README, no secrets in repo
10. Claude Code configs untouched throughout; no deletion or modification of .claude/ files
