---
slug: claude-code-to-opencode
status: drafting
intent: unclear
pending-action: write .omo/plans/claude-code-to-opencode.md
approach: Build Bifrost — an OpenCode plugin + Python companion bringing Claude Code parity via 6 features: memory (SQLite), context injection, skill bridge, permission audit, auto-mode classifier subagent, goal loop, and model fusion. Single-language companion (Python FastMCP), no nano-claude-code fork, no shell exec in skills, read-only permission migration, DEFAULT DENY classifier. v1 ships all 7 features; v2 adds consolidation + agent orchestration.
---

# Draft: claude-code-to-opencode

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| C1 | Create AGENTS.md with project context for skills-repo | active | .omo/drafts/claude-code-to-opencode.md |
| C2 | Map and migrate critical Claude Code plugins to OpenCode equivalents | active | .omo/drafts/claude-code-to-opencode.md |
| C3 | Skill parity audit: verify all 76 skills work identically in OpenCode | active | .omo/drafts/claude-code-to-opencode.md |
| C4 | Migrate personal/user-level skills (ai-galaxy, dl-tuning-playbook, feishu-kb, night-shift, ara-manager) | active | .omo/drafts/claude-code-to-opencode.md |
| C5 | Configure OpenCode permissions to match Claude Code safety profile | active | .omo/drafts/claude-code-to-opencode.md |
| C6 | Editor/IDE integration evaluation (VS Code, terminal experience) | deferred | .omo/drafts/claude-code-to-opencode.md |
| C7 | Bifrost companion (Python FastMCP server: SQLite, memory, skill loader, fusion dispatcher) | active | .omo/drafts/claude-code-to-opencode.md |
| C8 | Bifrost plugin (JS/TS: context injection, auto-mode classifier relay, goal loop trigger) | active | .omo/drafts/claude-code-to-opencode.md |
| C9 | Auto-mode classifier subagent (DEFAULT DENY, feedback learning) | active | .omo/drafts/claude-code-to-opencode.md |
| C10 | Goal loop (continuous agent iteration with memory reporting) | active | .omo/drafts/claude-code-to-opencode.md |
| C11 | Model fusion (parallel dispatch + synthesis) | active | .omo/drafts/claude-code-to-opencode.md |
| C12 | Skill bridge (verified top-10, argument substitution) | active | .omo/drafts/claude-code-to-opencode.md |
| C13 | Permission audit (read-only ConfigMigrate) | active | .omo/drafts/claude-code-to-opencode.md |
| C14 | Testing, documentation, opencode.json snippet | active | .omo/drafts/claude-code-to-opencode.md |

## Open assumptions (announced defaults)
<!-- Intent is UNCLEAR: research resolves ambiguity, defaults are adopted (not asked), and each is surfaced in the plan's human TL;DR for veto. -->
<!-- assumption | adopted default | rationale | reversible? -->
| A1 | User wants a gradual, reversible migration, not a hard cutover | All work is additive (new configs, new files); Claude Code configs remain untouched | Yes — delete new files to revert |
| A2 | DeepSeek routing stays the same | OpenCode already uses deepseek-v4-flash/pro via oh-my-openagent, matching Claude Code's ANTHROPIC_BASE_URL proxy | Yes |
| A3 | plugin parity prioritizes superpowers > playwright > frontend-design | superpowers is most-used (487 invocations), playwright enables browser testing, frontend-design is least critical for bioinformatics | Yes |
| A4 | User skills (ai-galaxy, dl-tuning-playbook, etc.) are essential and must migrate | These are tracked in Claude Code usage stats with high counts; they represent core workflows | Yes |
| A5 | MCP servers are deferred | Neither Claude Code nor OpenCode has user-configured MCP servers; no existing MCP workflows to break | Yes |
| A6 | Effort-level and agent-teams are deferred as OpenCode platform gaps | These require OpenCode core changes or oh-my-openagent extensions; not config-level fixes | Yes |

## Findings (cited - path:lines)

### Claude Code Feature Set (from librarian bg_6f5e256a)
- Skills: SKILL.md with rich frontmatter (model/effort/agent/allowed-tools), dynamic context injection (!`cmd`), string substitution ($ARGUMENTS, $CLAUDE_SESSION_ID). Discovery: ~/.claude/skills/, .claude/skills/, plugin skills.
- Permissions: deny→ask→allow evaluation order, gitignore-style path patterns, workspace trust, managed policies, permission modes (default/acceptEdits/plan/auto/dontAsk/bypassPermissions).
- CLAUDE.md: hierarchical @imports, .claude/rules/ path-scoped rules, auto-memory to ~/.claude/projects/<project>/memory/, CLAUDE.local.md.
- Hooks: 15+ lifecycle events (PreToolUse, PostToolUse, SessionStart, Stop, PreCompact, etc.) with command/http/mcp_tool/prompt/agent types and exit-code-based decisions.
- MCP: claude mcp add CLI, plugin MCP, channel support, tool search (deferred schema loading).
- Subagents: Explore/Plan/General-purpose built-in; custom agent .md files with tools/model/permissionMode/maxTurns/isolation: worktree.
- Agent Teams: multi-instance coordination (experimental, enabled via CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1).
- IDE: VS Code, JetBrains, Desktop App, Web (claude.ai/code).
- Worktrees: --worktree flag, WorktreeCreate/WorktreeRemove hooks, subagent isolation: worktree.
- Settings: Managed > CLI flags > Local > Project > User hierarchy; array merge, scalar override.
- Plugins: 7 active from anthropics/claude-plugins-official marketplace.

### OpenCode Feature Set (from librarian bg_6f7112d9)
- Skills: SKILL.md with name/description/license/compatibility/metadata frontmatter; embedded MCP servers in skills. Discovery: .opencode/skills/, ~/.config/opencode/skills/, .claude/skills/, .agents/skills/.
- Permissions: last-match-wins, pattern matching on tool input, per-agent overrides, doom_loop detection.
- AGENTS.md: project root or ~/.config/opencode/AGENTS.md; instructions array with globs/URLs; /init command.
- Hooks: Plugin-only events (tool.execute.before, tool.execute.after, session.*, etc.); no standalone hook config.
- MCP: opencode.json config, local (stdio) and remote (HTTP), OAuth support, remote config override (.well-known/opencode).
- Subagents: task() tool, built-in build/plan/general/explore/scout; custom agents via JSON or .md in .opencode/agents/.
- Plugin system: JS/TS files in .opencode/plugins/ or npm packages; custom tools via @opencode-ai/plugin.
- Sessions: SQLite storage, undo/redo (Git-powered), compaction, share, export/import.
- Todo: todowrite tool with content/status/priority.
- Config: remote > global > project > .opencode/directory; JSONC format; variable substitution ({env:}, {file:}).

### User's Claude Code Setup (from explore bg_869993b7)
- ~/.claude/settings.json: DeepSeek proxy, model routing (flash=sonnet/haiku, pro=opus/reasoning), effortLevel: xhigh, 7 plugins enabled, ENABLE_TOOL_SEARCH: true, CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: 1
- ~/.claude/skills/: 90 entries including 9 nature-* skills, 32 database skills, personal skills (ai-galaxy, dl-tuning-playbook, feishu-kb, night-shift, ara-manager, caveman, handoff, etc.)
- ~/.claude/plugins/: 10 official plugins installed, 7 active (superpowers v5.1.0, frontend-design, playwright, claude-md-management v1.0.0, feature-dev, agentforce-adlc v0.7.0, resend v1.0.0)
- ~/.claude/agents/project-reviewer.md: custom subagent (233 lines)
- ~/.claude/night-shift/config.json: Autonomy L2, 5M daily max tokens, off-peak dispatch 18:05
- ~/.claude/history.jsonl: 8,143 lines, 74 total sessions, 151,588 total messages
- skills-repo/.claude/settings.local.json: minimal permissions (mkdir, cp, curl, git add/commit/push, Read /tmp/**)
- NO hooks configured, NO custom slash commands, NO user-level CLAUDE.md (~/.claude/CLAUDE.md absent)
- 3 project CLAUDE.md files: MARLIN (266 lines), project_BCR_Tree (160 lines), LUMI-lab (69 lines)

### User's OpenCode Setup (from explore bg_1a011f1a)
- ~/.config/opencode/opencode.json: deepseek-v4-flash default, deepseek-v4-pro available, only oh-my-openagent plugin
- ~/.config/opencode/oh-my-openagent.json: 11 subagents (sisyphus, hephaestus, oracle, prometheus, metis, momus, librarian, explore, multimodal-looker, atlas, sisyphus-junior, canary), 9 categories
- skills-repo/.agents/skills/: 76 skills matching .claude/skills/ set
- NO AGENTS.md in skills-repo
- NO project-level opencode.json in skills-repo
- NO user-configured MCP servers
- 18 sessions (all today, ~$0.29 total cost)
- ~/.local/share/opencode/opencode.db: SQLite session storage

### Direct Exploration (this session)
- .claude/skills/ and .agents/skills/ both have 76 skills (identical sets)
- ~/.claude/skills/ has 90 entries (14 more: ai-galaxy, ara-manager, caveman, dl-tuning-playbook, feishu-kb, night-shift + category dirs)
- No .opencode/ directory in skills-repo

## Decisions (with rationale)

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | Create AGENTS.md for skills-repo FIRST | Foundation for all other config; enables project-specific context for OpenCode agents |
| D2 | Phase 1: config parity (AGENTS.md, permissions, project opencode.json) | No-code changes, immediate UX improvement, reversible |
| D3 | Phase 2: skill audit (verify all 76 skills load and work) | Skills are the core value; must confirm OpenCode compatibility before relying on them |
| D4 | Phase 3: personal skill migration (5 high-priority skills) | User's daily workflow depends on ai-galaxy, dl-tuning-playbook, feishu-kb, night-shift, ara-manager |
| D5 | Phase 4: plugin gap analysis (evaluate OpenCode alternatives for superpowers, playwright) | superpowers is most-used plugin; playwright enables browser testing; others are lower priority |
| D6 | Defer: IDE integration, worktrees, agent teams, effort level, hooks | These are OpenCode platform-level gaps requiring upstream changes or plugin development; document as feature requests |
| D7 | Keep Claude Code configs intact throughout | Gradual migration; no deletion of .claude/ files until user confirms OpenCode parity |

## Scope IN
- Create AGENTS.md for skills-repo with project context, conventions, and skill usage patterns
- Create project-level .opencode/opencode.json with permissions matching Claude Code's safety profile
- Audit all 76 skills in .agents/skills/ for OpenCode compatibility (SKILL.md format, frontmatter, scripts)
- Migrate 5 personal skills: ai-galaxy, dl-tuning-playbook, feishu-kb, night-shift, ara-manager
- Evaluate and map Claude Code plugins to OpenCode alternatives (superpowers → built-in + oh-my-openagent features)
- Document platform-level gaps as feature requests with clear requirements

## Scope OUT (Must NOT have)
- Do NOT delete or modify any Claude Code configuration files (.claude/, ~/.claude.json, etc.)
- Do NOT modify existing skills' functional behavior — only adapt format/paths for OpenCode compatibility
- Do NOT implement new OpenCode features or plugins (only configure existing capabilities)
- Do NOT attempt to replace Claude Code IDE integration (VS Code extension, JetBrains plugin)
- Do NOT change model routing or DeepSeek proxy configuration
- Do NOT create MCP servers (no existing MCP workflows to migrate)
- Do NOT attempt worktree isolation parity (OpenCode platform gap)

## Open questions
(None — all ambiguities resolved via research and best-practice defaults)

## Approval gate
status: approved
review-receipts:
  momus: APPROVE — 1 schema defect (learned_rules table missing from 1.2, fixed)
  oracle: REVISE — 3 architectural concerns (pre-filter, goal-loop isolation, MCP priority; addressed as execution notes)
approval-date: 2026-07-10
pending-action: none — plan complete at .omo/plans/claude-code-to-opencode.md
next: user runs /start-work to begin execution
