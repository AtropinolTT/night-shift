# Bifrost

**v0.2.2**. Security-hardened release. Not for production use.

An OpenCode plugin and Python FastMCP companion that bridges agent capabilities: persistent memory, tool call classification, goal-oriented agent loops, skill bridging, permission auditing, and multi-model synthesis.

---

## 1. Overview

Bifrost is a two-component system that sits between an OpenCode agent and its execution environment. A TypeScript plugin hooks into OpenCode's lifecycle (tool calls, commands, session events), relaying decisions through a local Python FastMCP companion server. The companion persists state to SQLite and orchestrates capabilities that need a long-lived process: classifier logic, skill discovery, memory search, and multi-model dispatch.

Think of it as a middleware layer. The agent keeps doing what it does (reading files, running tools, calling models), and Bifrost adds guardrails, memory, and multi-model reasoning alongside it.

### What problem does it solve?

Coding agents are powerful but stateless. Each session starts from scratch. There's no built-in memory of past decisions, no guardrails on which tools get invoked, no structured way to discover and load reusable skills, and no mechanism to compare what multiple models would say about the same prompt. Bifrost adds all of these as a plugin you install once, with configuration that travels with your project.

---

## 2. Features

### 1. Persistent Memory
Store and retrieve decisions, patterns, facts, and feedback across sessions. SQLite-backed with full-text search (FTS5). Scoped to user or project level. Soft-deletes preserve history while keeping queries clean. No external vector database required.

### 2. Context Injection
Session-aware context that the plugin and companion share. Tool calls carry session metadata so the classifier and goal loop understand what the agent is currently doing, not just what tool is about to be called.

### 3. Tool Call Classifier
**DEFAULT DENY policy.** Every tool call passes through a two-tier classifier: a sub-millisecond pre-filter for known safe tools (Read, Glob, Grep, LSP diagnostics), then a cheap-model dispatch for ambiguous calls. Falls back to ASK_USER on any failure. Overrides are logged and, after 5 consistent corrections, generate a learned rule for human review. Learned rules are never auto-applied.

### 4. Goal-Oriented Agent Loop
A classifier-gated simulation loop. Each turn an action executes, the classifier reviews it, and progress is assessed. Terminates on goal completion, 3 consecutive DENY decisions, cost ceiling exceeded, or max turns reached. Designed as a simulation harness first. Real agent execution can be layered on without changing the loop core.

### 5. Skill Bridge
Discover, load, and resolve skills from multiple search paths (`.agents/skills/`, `~/.claude/skills/`, `.claude/skills/`). Skills are parsed from YAML frontmatter with `$0`/`$NAME` argument substitution. A dedicated compatibility matrix (`SKILL_COMPAT.md`) tracks which workspace skills have been verified safe for bridge execution. Zero shell exec. Skills are text resources, not runnable scripts.

### 6. Permission Audit
Read-only migration from other coding agent config files to OpenCode format. Maps permission keys, model names, bash command allowlists, and flags. Filters secrets (API keys, tokens) automatically. Flags unmappable keys for manual review. Source files are never modified. The audit is a one-time display, not an auto-apply.

### 7. Model Fusion *(EXPERIMENTAL)*
**Labeled EXPERIMENTAL in all output.** Dispatch a single prompt to up to 3 models in parallel, then synthesize a unified answer from their responses. Includes per-model cost tracking, timeout resilience (partial failures don't block the fusion), and a configurable cost ceiling. The synthesis model is instructed to identify strong claims, resolve contradictions, and weight weaker responses less.

**v0.2.2+** The fusion skill is auto-installed to `~/.claude/skills/fusion/SKILL.md` when the plugin loads — making `/fusion` available as a global slash command in every OpenCode session, no project-level `.agents/skills/` file needed. Uses a FAST dispatch path via `opencode run --session` with preloaded sessions for ~3-5s response times.

### 8. Cost Tracking
Per-session cost summary via `session_cost_summary` MCP tool. Track token usage and dollar amounts across sessions.

### 9. Tokenizer Utility
Accurate token counting via `count_tokens` MCP tool, backed by `tiktoken`. Useful for prompt budget management before dispatching to models.

---

## 3. Prerequisites

- **OpenCode** with plugin support enabled
- **Python 3.10+** with `pip`
- **Node.js 18+** with `npm` (for the TypeScript plugin)
- **uv** (recommended, for running the companion; `pip` works as a fallback)

---

## 4. Installation

### Step 1: Clone the repository

```bash
git clone <repo-url> bifrost
cd bifrost
```

### Step 2: Install Python dependencies

```bash
pip install -r requirements.txt
```

The core dependency is `fastmcp`. The companion also uses `pyyaml` for configuration and `httpx` for HTTP calls.

### Step 3: Install plugin dependencies

```bash
cd plugin
npm install
cd ..
```

### Step 4: Install the plugin

Bifrost has two parts: a **TypeScript plugin** and a **Python companion** (MCP server).
Both must be configured in `opencode.json` (global at `~/.config/opencode/opencode.json` or per-project).

#### Option A: Published npm package (recommended)

Once published to npm, add the package name to the `plugin` array:

```jsonc
{
  "plugin": [
    "bifrost-plugin"
  ],
  "mcp": {
    "bifrost-companion": {
      "type": "local",
      "command": ["python3", "/path/to/bifrost/companion/server.py"],
      "enabled": true
    }
  }
}
```

> **Key detail**: The `mcp` key (not `mcpServers`) is used for MCP server configuration.
> The `command` must be a **single array** of command + arguments.
> OpenCode loads plugins from the `plugin` array by npm package name.

#### Option B: Local development (npm link)

For development before publishing to npm:

```bash
cd bifrost/plugin
npm link        # makes "bifrost-plugin" available as a local npm package
```

Then add to `opencode.json`:

```jsonc
{
  "plugin": [
    "oh-my-openagent@latest",
    "bifrost-plugin"
  ],
  "mcp": {
    "bifrost-companion": {
      "type": "local",
      "command": ["python3", "/path/to/bifrost/companion/server.py"],
      "enabled": true
    }
  }
}
```

#### Option C: Local plugin files (alternative)

Drop the compiled plugin file into `~/.config/opencode/plugins/bifrost.js`
(or `.opencode/plugins/bifrost.js` for per-project).
If the plugin needs npm dependencies, create a `~/.config/opencode/package.json`
with those dependencies — OpenCode runs `bun install` at startup to install them.

---

## 5. Configuration

### Plugin: `opencode.json`

The plugin is loaded via the `plugin` array (npm package name). No additional
`plugins` object is needed — OpenCode auto-discovers the plugin.

| Field | Type | Default | Description |
|---|---|---|---|
| `plugin[]` | `string[]` | `[]` | Add `"bifrost-plugin"` to load Bifrost from npm |

The companion MCP server is configured under the `mcp` key (not `mcpServers`).
See [Step 4](#step-4-install-the-plugin) for the correct config block.

### Companion: `config.yaml`

The companion looks for configuration in XDG-compliant paths:

1. `$XDG_CONFIG_HOME/bifrost/config.yaml`
2. `~/.bifrost/config.yaml`

All fields have sensible defaults. You only need to create this file if you want to customize behaviour.

| Field | Type | Default | Description |
|---|---|---|---|
| `model_for_classifier` | `string` | `deepseek-v4-flash` | Model to use for tool call classification |
| `model_for_fusion_synthesis` | `string` | `deepseek-v4-pro` | Model to use for synthesizing fusion results |
| `max_context_tokens` | `int` | `8000` | Maximum context window for injection |
| `max_turns_default` | `int` | `10` | Default max turns for goal loop |
| `cost_ceiling_default` | `float` | `1.00` | Default dollar ceiling for goal loop |
| `allowlisted_bash_commands` | `list[str]` | `["ls","git status","git diff","git log","pwd","echo","python --version","pip list"]` | Bash commands the classifier pre-filters as safe |

Example `~/.bifrost/config.yaml`:

```yaml
model_for_classifier: deepseek-v4-flash
model_for_fusion_synthesis: deepseek-v4-pro
max_turns_default: 15
cost_ceiling_default: 2.00
```

---

## 6. Architecture

```
┌──────────┐     ┌──────────────────────────────────┐     ┌──────────────────────────────┐
│          │     │  Plugin (TypeScript)              │     │  Companion (Python FastMCP)  │
│  User    │────▶│  bifrost/plugin/                  │────▶│  bifrost/companion/           │
│          │     │                                   │     │                               │
│  "Fix    │     │  index.ts                         │ MCP │  server.py  ─── config.py     │
│   this"  │     │   ├─ lifetime hooks                │stdio│   ├─ memory/    (SQLite+     │
│          │     │   ├─ global fusion skill installer │────▶│   │              FTS5)        │
│          │     │   ├─ classifier pre-filter         │     │   ├─ classifier/              │
│          │     │   ├─ mcp-relay.ts                 │     │   ├─ goal/                    │
│          │     │   ├─ logger.ts (~/.bifrost/logs/)  │     │   ├─ cost/     (tracker)      │
│          │     │   ├─ slash commands                │     │   ├─ skill/   (loader)        │
│          │     │   └─ tool registrations            │     │   ├─ utils/   (tokenizer)     │
│          │     │                                   │     │   ├─ permission/ (migrate)    │
│          │     │  STDIO → server.py                 │     │   ├─ context/                 │
│          │     │                                   │     │   └─ db.py    (connection)    │
│          │     │  MCP relay calls:                  │     │                               │
│          │     │   memory_*                         │     │  SQLite storage:              │
│          │     │   classify_tool_call               │     │   ~/.bifrost/bifrost.db       │
│          │     │   goal_loop                        │     │   ├─ memories                 │
│          │     │   fusion_dispatch_tool             │     │   ├─ memories_fts (FTS)       │
│          │     │   config_migrate / project         │     │   ├─ classifier_feedback      │
│          │     │   skill_load / skill_list          │     │   ├─ learned_rules            │
│          │     │   log_override                     │     │   └─ config                   │
│          │     │   session_cost_summary             │     │                               │
│          │     │   count_tokens                     │     │   Logs: ~/.bifrost/logs/      │
└──────────┘     └──────────────────────────────────┘     └──────────────────────────────┘
```

### Component roles

| Component | Language | Role |
|---|---|---|---|
| **Plugin** (`plugin/`) | TypeScript | Hooks into OpenCode lifecycle. Pre-filters known-safe tools locally to avoid unnecessary MCP round-trips. Relays classification, goals, fusion, and audit requests to the companion. Registers `/goal`, `/fusion`, `/audit-permissions`, `/review`, `/explain`, `/commit`, and `/test` slash commands. Includes circuit breaker for MCP relay resilience. Logs to `~/.bifrost/logs/plugin.log` via file-based logger. |
| **Companion** (`companion/`) | Python (FastMCP) | Long-lived server process. Owns all state (SQLite), all model dispatch, skill parsing, and configuration. Exposes 15+ MCP tools over stdio. Never modifies source files. |
| **SQLite** (`~/.bifrost/bifrost.db`) | Data | Persistent storage for memories, classifier feedback, learned rules, and configuration. Uses WAL journal mode for concurrent access. Full-text search via FTS5 virtual table. |

### Data flow: tool call classification

```
Agent calls tool
  → Plugin intercepts (permission.ask hook)
    → Pre-filter: known-safe? → ALLOW (0ms)
    → Relay to companion: classify_tool_call(…)
      → Classifier: two-tier (pre-filter then model dispatch)
      → Return ALLOW / DENY / ASK_USER
    → Plugin enforces decision
    → User override? → log_override(…) → learned_rules
```

### Data flow: slash command (two paths)

```
User types /fusion "prompt"
  → Plugin auto-installed global skill at ~/.claude/skills/fusion/SKILL.md
  → Auto-slash-command loads skill → agent executes

  FAST path (preloaded sessions):
    bash(opencode run --session ses_FLASH --model ...)  ─→ ~3s
    bash(opencode run --session ses_PRO  --model ...)  ─→ ~3s
    ↓
    All responses collected → synthesize (or skip via --fast)

  FRESH path (first use or --reset):
    task(category=quick, run_in_background=true)       ─→ ~50s
    task(category=unspecified-high, run_in_background=true) ─→ ~50s
    ↓
    Sessions cached → next call uses FAST path

  Output: EXPERIMENTAL — Model Fusion banner + per-model table + fused answer
```

---

## 7. Usage

### Memory commands

Bifrost exposes memory through MCP tools. The plugin wires these so the agent can use them naturally:

| Tool | What it does |
|---|---|
| `memory_save(type, content, scope)` | Store a memory (type: decision/pattern/fact/feedback) |
| `memory_search(query, scope, type_filter, limit)` | Full-text search across memories |
| `memory_list(scope, type_filter, limit)` | List memories with optional filtering |
| `memory_delete(memory_id)` | Soft-delete a memory by ID |

The agent can be instructed to store important decisions, discovered patterns, or user preferences. For example: "Remember that I prefer 2-space indentation in Python files."

### Slash commands

**`/goal "description"`**
Run a classifier-gated goal-oriented agent simulation. Each turn executes an action, the classifier reviews it, and progress is assessed. Terminates on goal completion, 3 consecutive DENY, cost ceiling, or max turns.

```
/goal "Fix all type errors in src/"
```

**`/fusion "prompt"`** *(EXPERIMENTAL)*
Dispatch a prompt to multiple models in parallel and synthesize a unified answer. All output is labeled EXPERIMENTAL. Cost ceiling: $0.50 per fusion.

```
/fusion "Compare async patterns in Rust vs TypeScript for a web server"
```

**`/audit-permissions [path]`**
Read-only audit of configuration from other coding agent tools. Maps permission keys and model names to OpenCode equivalents. Secrets are automatically filtered. Output is displayed, never auto-applied.

```
/audit-permissions
/audit-permissions ~/other-agent-config.json
```

**`/review [base-ref]`**  
Code review bridge. Displays a diff summary and invokes the `review` skill for a standards-and-spec review against a base reference (default: `HEAD~1`).

**`/explain <file or code>`**  
Code explanation bridge. Sends a file path or code snippet to the companion for an AI-generated explanation.

**`/commit [message]`**  
Smart commit bridge. Generates or accepts a commit message and invokes the `git-master` skill for atomic commits.

**`/test [target]`**  
Test runner bridge. Runs or delegates to the `tdd` skill for red-green-refactor testing workflow.

### MCP tools (for programmatic use)

The companion exposes these MCP tools over stdio. They are intended for the plugin to call, but can be invoked by any MCP client:

| Tool | Category |
|---|---|
| `version` | Returns `"bifrost v0.2.2"` |
| `echo` | Echoes a message back (health check) |
| `memory_save`, `memory_search`, `memory_list`, `memory_delete` | Persistent memory |
| `classify_tool_call` | Tool call classification |
| `log_override` | Log user override of classifier decision |
| `goal_loop` | Classifier-gated agent simulation |
| `fusion_dispatch_tool` | Multi-model dispatch and synthesis |
| `config_migrate` | Read-only config migration audit |
| `config_migrate_project` | Project-level config migration |
| `skill_load`, `skill_list` | Skill discovery and loading |
| `session_cost_summary` | Per-session cost tracking |
| `count_tokens` | Accurate token counting via tiktoken |

---

## 8. Skill Bridge

Bifrost discovers skills from three search paths (project-level `.agents/skills/`, user-level `~/.claude/skills/`, and repo-level `.claude/skills/`), parses their YAML frontmatter, and resolves `$0`/`$NAME` argument substitution. Skills are text resources loaded and returned to the agent. No shell execution.

### Compatibility

Not all workspace skills are compatible with Bifrost's skill bridge. A compatibility matrix is maintained at [`SKILL_COMPAT.md`](SKILL_COMPAT.md). As of v0.2.2:

- **9 skills** are **verified**: manually audited for zero shell exec, valid frontmatter, no dangerous patterns, and compatible argument substitution
- **74 skills** are **best-effort**: exist in the workspace but have not been verified
- **4 skills** are user-scope with unknown compatibility

To contribute a verification: read the skill's `SKILL.md`, check it against the criteria in `SKILL_COMPAT.md`, and open a PR updating its status.

### Loading a skill

```
skill_load("caveman") → returns resolved body + frontmatter
```

Skills with verified compatibility can be loaded and their instructions injected into the agent's context safely.

---

## 9. Known Limitations

**Classification is guidance, not enforcement.** The classifier returns ALLOW/DENY/ASK_USER decisions, but the plugin's enforcement depends on OpenCode's permission model. In some configurations, ASK_USER may default to ALLOW. Always review learned rules before activating them.

**Goal loop is simulation-only.** The loop accepts a list of simulated actions. It does not execute real tool calls. Real agent execution requires a model-backed loop (planned for a future release).

**Model fusion costs are approximate.** Token counts are coarsely estimated (`len(text) // 4`). Per-model pricing is hard-coded, not fetched from a live API. The synthesis model adds its own cost on top of the per-model dispatch.

**Skill bridge is text-only.** Skills are loaded and returned as text. The bridge does not execute skill instructions or invoke tools on behalf of the skill. Skills that require API keys, MCP server connections, or external tool dependencies are listed as best-effort.

**No distributed memory.** The SQLite database lives at `~/.bifrost/bifrost.db` on a single machine. There is no sync, replication, or shared memory across team members.

**Alpha software.** This is v0.2.2. APIs, MCP tool signatures, and config formats may change between releases. There is no migration path for breaking changes yet. The companion may crash on unexpected inputs. Do not run in production.

---

## 10. Contributing

Bifrost welcomes contributions. Before submitting, please:

1. **Open an issue** describing the bug or feature. Tag it with `bifrost`.
2. **Read the codebase.** The companion is organized by capability (memory, classifier, goal, fusion, skill, permission). Each subdirectory has a clear responsibility. The plugin is a single `index.ts` with well-commented hook registrations.
3. **Run the tests.** The companion has a test suite:
   ```bash
   cd bifrost
   python -m pytest tests/ -v
   ```
4. **Check LSP diagnostics.** Both the Python companion and TypeScript plugin should be clean:
   ```bash
   cd plugin && npx tsc --noEmit
   ```
5. **Keep skill verifications current.** If you add or modify a skill that the bridge loads, update `SKILL_COMPAT.md`.

### Areas that need help

- Live pricing API integration for cost tracking
- Goal loop with actual agent execution (beyond simulation)
- Skill compatibility verification for best-effort skills
- Fusion skill: per-model variant configuration, Minimax M3 provider support
- Comprehensive test coverage for the companion

---

## 11. License

MIT License. See [LICENSE](LICENSE).
