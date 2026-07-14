# Migration Specification: night-shift for Mainstream Agentic Tools

**Date:** 2026-07-14
**Status:** Draft
**Repo:** `/sibcb1/chuyanyilab1/tangjunjie/skills-repo`

---

## 1. Summary

This document specifies the migration of the `night-shift` skill from a Claude Code-centric path strategy to a **tool-agnostic** one compatible with mainstream agentic coding tools (Claude Code, Codex CLI, OpenCode, QoderCLI, and others).

The skill currently hardcodes `~/.claude/` paths in its SKILL.md, three shell scripts (`check-window.sh`, `estimate-cost.sh`, `parse-queue.sh`), and the cron dispatch prompt. Project discovery scans `~/.claude/projects/`, which does not exist in other tools. The migration must:

- Resolve configuration files (`pricing.json`, `config.json`, `state.json`) dynamically based on which tool is running.
- Replace all hardcoded paths with a single resolution script (`scripts/config-dir.sh`).
- Discover projects (NIGHTSHIFT.md files) across all tools' conventions.
- Make the skill loadable by any tool — via its native skill/plugin system or direct SKILL.md reference.
- Provide clear test and rollback strategy.

**Files to change:** SKILL.md (1 file), `scripts/check-window.sh`, `scripts/estimate-cost.sh`, `scripts/parse-queue.sh` (3 files), create `scripts/config-dir.sh` (1 new file), optional per-tool skill symlinks for discovery.

**No data schema changes.** All three data files (`config.json`, `pricing.json`, `state.json`) keep their existing JSON schemas.

---

## 2. Design Decisions

### Decision 1: Config Directory Resolution

**Problem:** Each tool stores user config in a different directory. Hardcoding any single path makes the skill dependent on that tool.

**Resolution — priority-chain script (`scripts/config-dir.sh`):**

A small shell script checks known tool directories in priority order, controlled by environment variable:

```
QODER_NS_CONFIG_DIR (env override, highest priority)
  → ~/.qoder/night-shift/    (QoderCLI)
  → ~/.claude/night-shift/    (Claude Code)
  → ~/.codex/night-shift/     (Codex CLI)
  → ~/.opencode/night-shift/  (OpenCode)
  → ~/.config/night-shift/    (generic fallback)
```

SKILL.md references `$(scripts/config-dir.sh)` everywhere a config path is needed — no hardcoded tool directory in the skill definition. Scripts use `$CONFIG_DIR` set from the same script.

**Optional symlink bridge:** `~/.qoder/night-shift/` → `~/.claude/night-shift/` preserves existing data location without moving files.

### Decision 2: Project Discovery

**Problem:** `parse-queue.sh` scans `~/.claude/projects/` for NIGHTSHIFT.md files, which doesn't exist in other tools.

**Resolution — multi-tool hybrid scan:**

1. **Explicit paths** from `config.json -> projects.paths` (highest priority, user-asserted).
2. **Tool-specific project directories** — scan known tool project roots in parallel:
   - `$QODER_PROJECT_DIR` and its siblings (QoderCLI)
   - `~/.claude/projects/` (Claude Code)
   - `~/.codex/*/` (Codex CLI — each project is a subdirectory)
   - `~/.opencode/` projects (OpenCode conventions)
3. **CWD-based fallback** — walk up from CWD to find `.qoder/` or NIGHTSHIFT.md.
4. Apply blacklist from `config.json -> projects.blacklist`.
5. Deduplicate by realpath.

### Decision 3: Skill Loading / Cron Prompt

**Problem:** The cron prompt hardcodes `~/.claude/skills/night-shift/SKILL.md`.

**Resolution — tool-agnostic prompt:**

```
Load the night-shift skill and follow its dispatch protocol precisely.
The skill is at the repo root. When loaded, it resolves its config
directory via `scripts/config-dir.sh`.
```

No tool-specific paths. The agent loading the cron prompt uses its native skill-discovery mechanism (Skill tool, plugin, or direct file read). The repo-relative path is resolved at cron-creation time via `SCRIPT_DIR` from the dispatch scripts.

### Decision 4: Script Path Resolution

**Resolution — CONFIG_DIR boilerplate in every script:**

```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$($SCRIPT_DIR/config-dir.sh)"
```

This gives:
- **Scripts work from any CWD** (cron-safe).
- **Tool-agnostic** — resolution happens at runtime via `config-dir.sh`.
- **Overridable** — set `QODER_NS_CONFIG_DIR` for testing or pinning.
- **Repo-root aware** — `$SCRIPT_DIR/..` locates the repo for cron prompt generation.

### Decision 5: Tool-Specific Skill Symlinks

**Problem:** Each tool has a different skill discovery directory. A symlink in only `.qoder/skills/` doesn't help Claude Code or Codex CLI.

**Resolution — per-tool symlinks from the canonical source:**

The canonical skill source (SKILL.md + scripts) lives at the repo root. Tool-specific discovery directories get symlinks:

| Tool | Symlink location | Target |
|------|-----------------|--------|
| QoderCLI | `.qoder/skills/night-shift` | `../../.agents/skills/night-shift` (→ root) |
| Claude Code | `~/.claude/skills/night-shift` | Already exists |
| Codex CLI | `~/.codex/skills/night-shift` | → repo root or `.agents/skills/night-shift` |
| OpenCode | TBD (tool-specific) | → repo root |

These are discovered automatically by each tool at startup. No tool needs to know about the others' symlinks.

### Decision 6: Testing Approach

| File | Test | Criteria |
|------|------|----------|
| `config-dir.sh` | Run with different tool directories present/absent | Correct priority resolution |
| `check-window.sh` | `--simulate peak --json` from `/tmp` | Valid JSON, correct window |
| `estimate-cost.sh` | `--tokens 100k --model pro --window peak --json` | Valid JSON with premium |
| `parse-queue.sh` | `--discover`, `--all`, `--project <path>` | Valid JSON structure |
| All scripts | Run from any CWD with `QODER_NS_CONFIG_DIR` override | Output matches baseline |
| SKILL.md | `grep` for hardcoded tool paths | Zero matches |
| Per-tool symlinks | Each symlink resolves to root SKILL.md | All pass |

---

## 3. File-by-File Change Plan

### File 0 (NEW): `scripts/config-dir.sh`

```bash
#!/bin/bash
# Resolve the night-shift config directory across agentic tools.
# Priority: QODER_NS_CONFIG_DIR > .qoder > .claude > .codex > .opencode > .config
CONFIG_DIR="${QODER_NS_CONFIG_DIR:-}"
if [[ -z "$CONFIG_DIR" ]]; then
  for dir in "$HOME/.qoder/night-shift" "$HOME/.claude/night-shift" \
             "$HOME/.codex/night-shift" "$HOME/.opencode/night-shift" \
             "$HOME/.config/night-shift"; do
    if [[ -d "$dir" ]]; then
      CONFIG_DIR="$dir"
      break
    fi
  done
fi
# Last resort: default to .qoder (will be created on first state write)
echo "${CONFIG_DIR:-$HOME/.qoder/night-shift}"
```

### File 1: SKILL.md

**Replace all hardcoded `~/.claude/night-shift/` references** with `$(scripts/config-dir.sh)`:

| Line(s) | Old | New |
|---------|-----|-----|
| 19 | `` `~/.claude/night-shift/pricing.json` `` | `` `$(scripts/config-dir.sh)/pricing.json` `` |
| 111 | `` `~/.claude/night-shift/pricing.json` `` | `` `$(scripts/config-dir.sh)/pricing.json` `` |
| 161 | `` `~/.claude/night-shift/config.json` `` | `` `$(scripts/config-dir.sh)/config.json` `` |
| 162 | `` `~/.claude/night-shift/state.json` `` | `` `$(scripts/config-dir.sh)/state.json` `` |
| 196 | `` `~/.claude/night-shift/config.json` `` | `` `$(scripts/config-dir.sh)/config.json` `` |
| 213 | `` `~/.claude/night-shift/state.json` `` | `` `$(scripts/config-dir.sh)/state.json` `` |
| 309 | `` `~/.claude/night-shift/state.json` `` | `` `$(scripts/config-dir.sh)/state.json` `` |
| 343 | `` `~/.claude/skills/night-shift/SKILL.md` `` | Tool-agnostic cron prompt (see Decision 3) |
| 347 | `~/.claude/night-shift/config.json` | `$(scripts/config-dir.sh)/config.json` |
| 407 | `` `~/.claude/night-shift/` `` | `` `$(scripts/config-dir.sh)` `` |

**Configuration Files section header:**
```
**Config directory:** Run `scripts/config-dir.sh` to resolve the active directory.
Supported: QoderCLI (`.qoder/`), Claude Code (`.claude/`), Codex CLI (`.codex/`),
OpenCode (`.opencode/`). Set `QODER_NS_CONFIG_DIR` to override.
```

### File 2: `scripts/check-window.sh`

| Line | Change |
|------|--------|
| +2 (after line 11) | Add `SCRIPT_DIR` + `CONFIG_DIR` boilerplate |
| 3 (doc comment) | Update to not reference `~/.claude/` |
| 12 | `PRICING_FILE="$CONFIG_DIR/pricing.json"` |

### File 3: `scripts/estimate-cost.sh`

| Line | Change |
|------|--------|
| +2 (after line 13) | Add `SCRIPT_DIR` + `CONFIG_DIR` boilerplate |
| 3 (doc comment) | Update to not reference `~/.claude/` |
| 41 | `NS_PRICING_FILE="$CONFIG_DIR/pricing.json"` |

### File 4: `scripts/parse-queue.sh`

| Line | Change |
|------|--------|
| +2 (after line 13) | Add `SCRIPT_DIR` + `CONFIG_DIR` boilerplate |
| 28 | `state_file="$CONFIG_DIR/state.json"` |
| 214-265 | Rewrite `find_queues()` with multi-tool hybrid scan |

### File 5: `.qoder/skills/night-shift` (symlink for QoderCLI)

```bash
cd .qoder/skills
ln -s ../../.agents/skills/night-shift night-shift
```

### File 6: `~/.codex/skills/night-shift` (symlink for Codex CLI)

```bash
mkdir -p ~/.codex/skills
ln -s /sibcb1/chuyanyilab1/tangjunjie/skills-repo ~/.codex/skills/night-shift
```

### File 7 (optional): `~/.qoder/night-shift/` symlink bridge

Preserves backward compatibility with existing Claude Code data without moving files:

```bash
mkdir -p ~/.qoder && ln -s ~/.claude/night-shift ~/.qoder/night-shift
```

---

## 4. Migration Procedure

### Phase 1: Preparation
- [ ] Verify current scripts work (capture baseline output)
- [ ] Verify `~/.claude/night-shift/` files are valid JSON
- [ ] List current tool project dirs for comparison: `ls ~/.claude/projects/`

### Phase 2: Create `scripts/config-dir.sh`
- [ ] Write the config-dir.sh script
- [ ] Test: `QODER_NS_CONFIG_DIR=/tmp/test ./scripts/config-dir.sh` → `/tmp/test`
- [ ] Test: without env var, with `~/.qoder/night-shift/` missing → falls through chain

### Phase 3: Update scripts
- [ ] `check-window.sh` — boilerplate + path change
- [ ] `estimate-cost.sh` — boilerplate + path change
- [ ] `parse-queue.sh` — boilerplate + path changes + `find_queues()` rewrite
- [ ] Test each from `/tmp` (simulating cron context)

### Phase 4: Update SKILL.md
- [ ] Replace 10 hardcoded `~/.claude/` references
- [ ] Update cron prompt to tool-agnostic version
- [ ] Update Configuration Files section header
- [ ] Verify: `grep -c '~/.claude/' SKILL.md` == 0

### Phase 5: Create skill symlinks
- [ ] `mkdir -p .agents/skills/night-shift && ln -s ../../SKILL.md .agents/skills/night-shift/SKILL.md && ln -s ../../scripts .agents/skills/night-shift/scripts`
- [ ] `.qoder/skills/night-shift` → `../../.agents/skills/night-shift`
- [ ] `~/.codex/skills/night-shift` → repo root

### Phase 6: End-to-end verification
- [ ] Run all 3 scripts from `/tmp` without env override
- [ ] Run with `QODER_NS_CONFIG_DIR="$HOME/.claude/night-shift"` — matches baseline
- [ ] Verify each tool can discover the skill

---

## 5. Rollback Plan

| Phase | Rollback command |
|-------|-----------------|
| Phase 2 (config-dir.sh) | `rm scripts/config-dir.sh` |
| Phase 3 (scripts) | `git checkout -- scripts/*.sh` |
| Phase 4 (SKILL.md) | `git checkout -- SKILL.md` |
| Phase 5 (symlinks) | `rm .qoder/skills/night-shift && rm -rf .agents/skills/night-shift && rm -f ~/.codex/skills/night-shift` |

**Full rollback:**
```bash
cd /sibcb1/chuyanyilab1/tangjunjie/skills-repo
git checkout -- SKILL.md scripts/check-window.sh scripts/estimate-cost.sh scripts/parse-queue.sh
rm -f scripts/config-dir.sh
rm -f .qoder/skills/night-shift
rm -rf .agents/skills/night-shift
rm -f ~/.codex/skills/night-shift
```

**Rollback triggers:**
- Any Phase 6 verification step fails
- Output differs from pre-migration baseline when using `QODER_NS_CONFIG_DIR` override
- Any tool fails to discover or load the skill

---

## 6. Verification Checklist

### Data Integrity
- [ ] All three config files valid JSON after migration
- [ ] No data duplication across tool directories

### Script Function (from arbitrary CWD)
- [ ] `check-window.sh --simulate peak --json` returns `"window": "peak"`
- [ ] `check-window.sh --simulate off-peak --json` returns `"window": "off-peak"`
- [ ] `estimate-cost.sh --tokens 100000 --model pro --window peak --json` returns valid cost
- [ ] `parse-queue.sh --all` returns valid JSON with `projects` key

### Backward Compatibility
- [ ] `QODER_NS_CONFIG_DIR="$HOME/.claude/night-shift" check-window.sh --simulate peak --json` matches pre-migration baseline
- [ ] `QODER_NS_CONFIG_DIR="$HOME/.claude/night-shift" estimate-cost.sh --tokens 50000 --model flash --window off-peak --json` matches baseline

### Config Resolution
- [ ] `scripts/config-dir.sh` returns correct priority-ordered directory
- [ ] Falls through chain when higher-priority dirs missing
- [ ] `QODER_NS_CONFIG_DIR` override works

### SKILL.md Cleanliness
- [ ] `grep -c '~/.claude/' SKILL.md` returns 0 (no hardcoded tool paths)
- [ ] `grep -c 'config-dir.sh' SKILL.md` >= 10 (all config references dynamic)

### Multi-Tool Discovery
- [ ] `.qoder/skills/night-shift/SKILL.md` resolves to root SKILL.md
- [ ] `~/.codex/skills/night-shift/` resolves to repo root
- [ ] `~/.claude/skills/night-shift/` still works (unchanged)

---

## Appendix A: `scripts/config-dir.sh` (final)

```bash
#!/bin/bash
# Resolve the night-shift config directory across agentic tools.
# Priority: QODER_NS_CONFIG_DIR > .qoder > .claude > .codex > .opencode > .config
set -euo pipefail

CONFIG_DIR="${QODER_NS_CONFIG_DIR:-}"
if [[ -z "$CONFIG_DIR" ]]; then
  for dir in "$HOME/.qoder/night-shift" "$HOME/.claude/night-shift" \
             "$HOME/.codex/night-shift" "$HOME/.opencode/night-shift" \
             "$HOME/.config/night-shift"; do
    if [[ -d "$dir" ]]; then
      CONFIG_DIR="$dir"
      break
    fi
  done
fi
echo "${CONFIG_DIR:-$HOME/.qoder/night-shift}"
```

## Appendix B: SCRIPT_DIR Boilerplate (add to each script)

```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$($SCRIPT_DIR/config-dir.sh)"
```

## Appendix C: Path Reference Map

| Before (hardcoded) | After (dynamic) | Resolution |
|---|---|---|
| `$HOME/.claude/night-shift/pricing.json` | `$CONFIG_DIR/pricing.json` | `config-dir.sh` → tool-appropriate dir |
| `$HOME/.claude/night-shift/config.json` | `$CONFIG_DIR/config.json` | same |
| `$HOME/.claude/night-shift/state.json` | `$CONFIG_DIR/state.json` | same |
| `~/.claude/skills/night-shift/SKILL.md` | Tool-agnostic cron prompt + per-tool symlinks | Each tool discovers via its native mechanism |
| `~/.claude/projects/` scan | Multi-tool hybrid: config paths → tool project dirs → CWD walk | All tools' projects found |

## Appendix D: Tool Directory Reference

| Tool | Config dir | Skills dir | Projects dir |
|------|-----------|------------|-------------|
| Claude Code | `~/.claude/` | `~/.claude/skills/` | `~/.claude/projects/` |
| QoderCLI | `~/.qoder/` | `.qoder/skills/` (project) / `~/.qoder/skills/` (user) | Project root + siblings |
| Codex CLI | `~/.codex/` | `~/.codex/skills/` | `~/.codex/*/` (subdirs) |
| OpenCode | `~/.opencode/` | TBD | TBD |
| Generic | `~/.config/` | — | — |
