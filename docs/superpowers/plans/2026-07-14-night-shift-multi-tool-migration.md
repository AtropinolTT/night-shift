# Night-Shift Multi-Tool Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the night-shift skill fully tool-agnostic across Claude Code, Codex CLI, OpenCode, and QoderCLI by replacing hardcoded `~/.claude/` paths with a dynamic resolution script.

**Architecture:** A new `scripts/config-dir.sh` resolves the config directory via a priority chain (env var → `.qoder/` → `.claude/` → `.codex/` → `.opencode/` → `.config/`). Three existing scripts reference it via `$CONFIG_DIR`. SKILL.md references it via `$(scripts/config-dir.sh)`. Per-tool symlinks enable each tool to discover the skill.

**Tech Stack:** Bash 4+, Python 3 (existing), symlinks. No new dependencies.

## Global Constraints

- No data schema changes — `pricing.json`, `config.json`, `state.json` keep existing JSON schemas.
- All existing `~/.claude/` paths must be replaced — zero remaining after migration.
- Backward compatible: set `QODER_NS_CONFIG_DIR=$HOME/.claude/night-shift` to restore old behavior.
- Scripts must work from any CWD (cron-safe).
- Every change must be independently testable.

---

### Task 1: Create `scripts/config-dir.sh`

**Files:**
- Create: `scripts/config-dir.sh`
- Test: manual resolution tests

**Interfaces:**
- Produces: `scripts/config-dir.sh` — prints the resolved config directory path to stdout.
  - Reads `QODER_NS_CONFIG_DIR` env var (highest priority).
  - Falls through known tool directories in priority order.
  - Defaults to `~/.qoder/night-shift/` if nothing exists.
- Consumes: nothing.

- [ ] **Step 1: Create the script**

```bash
#!/bin/bash
# Resolve night-shift config directory across agentic tools.
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

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/config-dir.sh
```

- [ ] **Step 3: Test env override**

```bash
QODER_NS_CONFIG_DIR=/tmp/test-ns ./scripts/config-dir.sh
```
Expected output: `/tmp/test-ns`

- [ ] **Step 4: Test fallback chain**

```bash
./scripts/config-dir.sh
```
Expected output: `~/.qoder/night-shift` (first in chain, may not exist yet — that's OK, it's the default)

- [ ] **Step 5: Test claude fallback**

```bash
QODER_NS_CONFIG_DIR="" mv ~/.qoder/night-shift ~/.qoder/night-shift.bak 2>/dev/null; ./scripts/config-dir.sh; QODER_NS_CONFIG_DIR="" mv ~/.qoder/night-shift.bak ~/.qoder/night-shift 2>/dev/null
```
Expected output: `$HOME/.claude/night-shift` (because that dir exists)

- [ ] **Step 6: Commit**

```bash
git add scripts/config-dir.sh
git commit -m "feat(night-shift): add tool-agnostic config directory resolver"
```

---

### Task 2: Update `scripts/check-window.sh`

**Files:**
- Modify: `scripts/check-window.sh`
- Test: run from `/tmp` with `--simulate` flags

**Interfaces:**
- Consumes: `scripts/config-dir.sh` (Task 1) for `$CONFIG_DIR`
- Produces: updated `check-window.sh` with no hardcoded paths

- [ ] **Step 1: Edit the doc comment and add boilerplate**

Replace line 3 comment and add 2 lines after line 10:

Old line 3: `# Reads peak hour definitions from ~/.claude/night-shift/pricing.json`

New lines 3-5:
```
# Reads peak hour definitions from $(scripts/config-dir.sh)/pricing.json
```

After line 10 (`set -euo pipefail`), insert:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$($SCRIPT_DIR/config-dir.sh)"
```

- [ ] **Step 2: Replace the hardcoded path on line 12**

Old:
```bash
PRICING_FILE="$HOME/.claude/night-shift/pricing.json"
```
New:
```bash
PRICING_FILE="$CONFIG_DIR/pricing.json"
```

- [ ] **Step 3: Test from repo root**

```bash
./scripts/check-window.sh --simulate peak --json
```
Expected output: valid JSON with `"window": "peak"`

```bash
./scripts/check-window.sh --simulate off-peak --json
```
Expected output: valid JSON with `"window": "off-peak"`

- [ ] **Step 4: Test from /tmp (simulating cron)**

```bash
cd /tmp && /sibcb1/chuyanyilab1/tangjunjie/skills-repo/scripts/check-window.sh --simulate peak --json
```
Expected output: same valid JSON from any CWD

- [ ] **Step 5: Commit**

```bash
git add scripts/check-window.sh
git commit -m "feat(night-shift): make check-window.sh tool-agnostic via config-dir.sh"
```

---

### Task 3: Update `scripts/estimate-cost.sh`

**Files:**
- Modify: `scripts/estimate-cost.sh`
- Test: run with sample args

**Interfaces:**
- Consumes: `scripts/config-dir.sh` for `$CONFIG_DIR`
- Produces: updated `estimate-cost.sh` with no hardcoded paths

- [ ] **Step 1: Edit doc comment and add boilerplate**

Replace line 3:
Old: `# Reads pricing from ~/.claude/night-shift/pricing.json`
New: `# Reads pricing from $(scripts/config-dir.sh)/pricing.json`

After line 12 (`set -euo pipefail`), insert:
```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$($SCRIPT_DIR/config-dir.sh)"
```

- [ ] **Step 2: Replace the hardcoded path on line 41**

Old:
```bash
export NS_PRICING_FILE="$HOME/.claude/night-shift/pricing.json"
```
New:
```bash
export NS_PRICING_FILE="$CONFIG_DIR/pricing.json"
```

- [ ] **Step 3: Test from repo root**

```bash
./scripts/estimate-cost.sh --tokens 100000 --model pro --window off-peak --json
```
Expected output: valid JSON with cost estimate

```bash
./scripts/estimate-cost.sh --tokens 100000 --model flash --window peak --json
```
Expected output: valid JSON with peak premium

- [ ] **Step 4: Test from /tmp**

```bash
cd /tmp && /sibcb1/chuyanyilab1/tangjunjie/skills-repo/scripts/estimate-cost.sh --tokens 50000 --model pro --window off-peak --json
```
Expected output: same valid JSON

- [ ] **Step 5: Commit**

```bash
git add scripts/estimate-cost.sh
git commit -m "feat(night-shift): make estimate-cost.sh tool-agnostic via config-dir.sh"
```

---

### Task 4: Update `scripts/parse-queue.sh`

**Files:**
- Modify: `scripts/parse-queue.sh`
- Test: run with `--discover`, `--all`, `--project`

**Interfaces:**
- Consumes: `scripts/config-dir.sh` for `$CONFIG_DIR`
- Produces: updated `parse-queue.sh` with no hardcoded paths and multi-tool project discovery

- [ ] **Step 1: Add boilerplate after line 10 (`set -euo pipefail`)**

```bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$($SCRIPT_DIR/config-dir.sh)"
```

- [ ] **Step 2: Replace state_file path on line 28**

Old:
```bash
local state_file="$HOME/.claude/night-shift/state.json"
```
New:
```bash
local state_file="$CONFIG_DIR/state.json"
```

- [ ] **Step 3: Rewrite `find_queues()` (lines 213-265)**

Replace the entire function with:

```bash
# --- Discover project queue files across all tools ---
find_queues() {
  local queues=()
  local CONFIG_FILE="$CONFIG_DIR/config.json"

  # Source 1: Explicit paths from config.json
  if [[ -f "$CONFIG_FILE" ]]; then
    export NS_CONFIG_FILE="$CONFIG_FILE"
    local extra
    extra=$(python3 -c "
import json, os
try:
    with open(os.environ['NS_CONFIG_FILE']) as f:
        cfg = json.load(f)
    for p in cfg.get('projects',{}).get('paths',[]):
        q = os.path.join(os.path.expanduser(p), 'NIGHTSHIFT.md')
        if os.path.exists(q):
            print(q)
except: pass
" 2>/dev/null)
    if [[ -n "$extra" ]]; then
      while IFS= read -r q; do
        queues+=("$q")
      done <<< "$extra"
    fi
  fi

  # Source 2: Claude Code projects directory
  if [[ -d "$HOME/.claude/projects" ]]; then
    while IFS= read -r q; do
      if [[ -f "$q" ]]; then queues+=("$q"); fi
    done < <(find "$HOME/.claude/projects" -maxdepth 2 -name 'NIGHTSHIFT.md' 2>/dev/null || true)
  fi

  # Source 3: Codex CLI projects (each subdirectory)
  if [[ -d "$HOME/.codex" ]]; then
    while IFS= read -r q; do
      if [[ -f "$q" ]]; then queues+=("$q"); fi
    done < <(find "$HOME/.codex" -maxdepth 2 -name 'NIGHTSHIFT.md' 2>/dev/null || true)
  fi

  # Source 4: QoderCLI project siblings via CWD walk
  local probe="$PWD"
  while [[ "$probe" != "/" ]]; do
    if [[ -f "$probe/NIGHTSHIFT.md" ]]; then
      queues+=("$probe/NIGHTSHIFT.md")
    fi
    probe="$(dirname "$probe")"
  done

  # Source 5: QODER_PROJECT_DIR siblings
  if [[ -n "${QODER_PROJECT_DIR:-}" && -d "$QODER_PROJECT_DIR" ]]; then
    local parent
    parent="$(dirname "$QODER_PROJECT_DIR")"
    while IFS= read -r candidate; do
      local nf="$candidate/NIGHTSHIFT.md"
      if [[ -f "$nf" ]]; then
        # Avoid duplicates with Source 4
        local already=false
        for q in "${queues[@]}"; do
          if [[ "$(realpath "$q" 2>/dev/null)" == "$(realpath "$nf" 2>/dev/null)" ]]; then
            already=true; break
          fi
        done
        ! $already && queues+=("$nf")
      fi
    done < <(find "$parent" -maxdepth 1 -type d 2>/dev/null || true)
  fi

  # Dedup by realpath
  if [[ ${#queues[@]} -gt 1 ]]; then
    local seen_paths=()
    local deduped=()
    for q in "${queues[@]}"; do
      local rp
      rp=$(realpath "$q" 2>/dev/null || echo "$q")
      local skip=false
      for sp in "${seen_paths[@]}"; do
        if [[ "$sp" == "$rp" ]]; then skip=true; break; fi
      done
      if ! $skip; then
        seen_paths+=("$rp")
        deduped+=("$q")
      fi
    done
    printf '%s\n' "${deduped[@]}"
  else
    printf '%s\n' "${queues[@]}"
  fi
}
```

Also update the config.json read inside `reset_midnight_budget()` — it's called at line 281 in the `all` mode. There's no hardcoded config.json path there, but the `CONFIG_FILE="$CONFIG_DIR/config.json"` is already used in `find_queues()`. The `reset_midnight_budget()` function reads state.json, which we already fixed at line 28.

- [ ] **Step 4: Test basic functionality**

```bash
./scripts/parse-queue.sh --discover
```
Expected output: list of NIGHTSHIFT.md paths (may be empty — that's fine)

```bash
./scripts/parse-queue.sh --all
```
Expected output: valid JSON with `last_scan` and `projects` keys

- [ ] **Step 5: Test from /tmp**

```bash
cd /tmp && /sibcb1/chuyanyilab1/tangjunjie/skills-repo/scripts/parse-queue.sh --all
```
Expected output: same valid JSON

- [ ] **Step 6: Commit**

```bash
git add scripts/parse-queue.sh
git commit -m "feat(night-shift): make parse-queue.sh tool-agnostic with multi-tool project discovery"
```

---

### Task 5: Update `SKILL.md` Path References

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: Replace line 19**

Old: `**Pricing source:** `~/.claude/night-shift/pricing.json` — read this file for`
New: `**Pricing source:** `$(scripts/config-dir.sh)/pricing.json` — read this file for`

- [ ] **Step 2: Replace line 111**

Old: `Read `~/.claude/night-shift/pricing.json` for current rates. Route by`
New: `Read `$(scripts/config-dir.sh)/pricing.json` for current rates. Route by`

- [ ] **Step 3: Replace line 161**

Old: `3. Read `~/.claude/night-shift/config.json` for budget and autonomy level.`
New: `3. Read `$(scripts/config-dir.sh)/config.json` for budget and autonomy level.`

- [ ] **Step 4: Replace line 162**

Old: `4. Read `~/.claude/night-shift/state.json` for today's spend.`
New: `4. Read `$(scripts/config-dir.sh)/state.json` for today's spend.`

- [ ] **Step 5: Replace line 196**

Old: `Show config. With `--set`, update `~/.claude/night-shift/config.json`.`
New: `Show config. With `--set`, update `$(scripts/config-dir.sh)/config.json`.`

- [ ] **Step 6: Replace line 213**

Old: `Check budget in `~/.claude/night-shift/state.json`:`
New: `Check budget in `$(scripts/config-dir.sh)/state.json`:`

- [ ] **Step 7: Replace line 309**

Old: `Update `~/.claude/night-shift/state.json`:`
New: `Update `$(scripts/config-dir.sh)/state.json`:`

- [ ] **Step 8: Replace lines 342-348 (cron prompt)**

Old block:
```
You have the night-shift skill at ~/.claude/skills/night-shift/SKILL.md.
First: read the SKILL.md file and follow its dispatch protocol precisely.
Then: check the current pricing window, scan all NIGHTSHIFT.md files,
and dispatch pending jobs within budget. Update queue status after each job.
Follow the autonomy rules from ~/.claude/night-shift/config.json.
```

New block:
```
Load the night-shift skill and follow its dispatch protocol precisely.
The skill resolves its config directory via `scripts/config-dir.sh`.
Check the current pricing window, scan all NIGHTSHIFT.md files,
and dispatch pending jobs within budget. Update queue status after each job.
```

- [ ] **Step 9: Replace lines 405-413 (Configuration Files section)**

Old:
```
## Configuration Files

All under `~/.claude/night-shift/`:

| File | Purpose | Editable? |
|------|---------|-----------|
| `pricing.json` | Peak windows, model rates | ... |
| `config.json` | Autonomy, budget, thresholds, schedule | ... |
| `state.json` | Runtime state (spend, cron IDs, day) | ... |
```

New:
```
## Configuration Files

Config directory resolved by `scripts/config-dir.sh`:
- `QODER_NS_CONFIG_DIR` env override (highest priority)
- `~/.qoder/night-shift/` (QoderCLI)
- `~/.claude/night-shift/` (Claude Code)
- `~/.codex/night-shift/` (Codex CLI)
- `~/.opencode/night-shift/` (OpenCode)

| File | Purpose | Editable? |
|------|---------|-----------|
| `pricing.json` | Peak windows, model rates | ... |
| `config.json` | Autonomy, budget, thresholds, schedule | ... |
| `state.json` | Runtime state (spend, cron IDs, day) | ... |
```

- [ ] **Step 10: Verify no hardcoded paths remain**

```bash
grep -n '~/.claude/' SKILL.md
```
Expected: no output (zero matches)

- [ ] **Step 11: Commit**

```bash
git add SKILL.md
git commit -m "feat(night-shift): replace hardcoded paths with dynamic config-dir.sh references"
```

---

### Task 6: Create Skill Symlinks for Multi-Tool Discovery

**Files:**
- Create: `.agents/skills/night-shift/SKILL.md` → `../../SKILL.md`
- Create: `.agents/skills/night-shift/scripts` → `../../scripts`
- Create: `.qoder/skills/night-shift` → `../../.agents/skills/night-shift`
- Create: `~/.codex/skills/night-shift` → repo root
- Optional: `~/.qoder/night-shift` → `~/.claude/night-shift` (symlink bridge)

- [ ] **Step 1: Create canonical skill source in `.agents/skills/`**

```bash
cd /sibcb1/chuyanyilab1/tangjunjie/skills-repo
mkdir -p .agents/skills/night-shift
ln -s ../../SKILL.md .agents/skills/night-shift/SKILL.md
ln -s ../../scripts .agents/skills/night-shift/scripts
```

- [ ] **Step 2: Create QoderCLI skill symlink**

```bash
cd /sibcb1/chuyanyilab1/tangjunjie/skills-repo/.qoder/skills
ln -s ../../.agents/skills/night-shift night-shift
```

- [ ] **Step 3: Create Codex CLI skill symlink**

```bash
mkdir -p ~/.codex/skills
ln -s /sibcb1/chuyanyilab1/tangjunjie/skills-repo ~/.codex/skills/night-shift
```

- [ ] **Step 4: Verify all symlinks resolve**

```bash
test -f /sibcb1/chuyanyilab1/tangjunjie/skills-repo/.agents/skills/night-shift/SKILL.md && echo "agents SKILL.md OK"
test -d /sibcb1/chuyanyilab1/tangjunjie/skills-repo/.agents/skills/night-shift/scripts && echo "agents scripts OK"
test -f /sibcb1/chuyanyilab1/tangjunjie/skills-repo/.qoder/skills/night-shift/SKILL.md && echo "qoder SKILL.md OK"
test -f ~/.codex/skills/night-shift/SKILL.md && echo "codex SKILL.md OK"
```

- [ ] **Step 5: Create optional symlink bridge for backward compat**

```bash
if [[ ! -d "$HOME/.qoder/night-shift" ]]; then
  ln -s "$HOME/.claude/night-shift" "$HOME/.qoder/night-shift"
  diff "$HOME/.qoder/night-shift/pricing.json" "$HOME/.claude/night-shift/pricing.json" && echo "Bridge OK: files match"
fi
```

- [ ] **Step 6: Commit**

```bash
cd /sibcb1/chuyanyilab1/tangjunjie/skills-repo
git add .agents/skills/night-shift .qoder/skills/night-shift
git commit -m "feat(night-shift): add skill symlinks for QoderCLI and Codex CLI discovery"
```

---

### Task 7: End-to-End Verification

- [ ] **Step 1: All 3 scripts from /tmp without env override**

```bash
cd /tmp
REPO=/sibcb1/chuyanyilab1/tangjunjie/skills-repo
$REPO/scripts/check-window.sh --simulate peak --json
$REPO/scripts/estimate-cost.sh --tokens 100000 --model pro --window off-peak --json
$REPO/scripts/parse-queue.sh --all
```
All three must return valid JSON with no errors.

- [ ] **Step 2: Backward compatibility with old path**

```bash
QODER_NS_CONFIG_DIR="$HOME/.claude/night-shift" $REPO/scripts/check-window.sh --simulate peak --json
QODER_NS_CONFIG_DIR="$HOME/.claude/night-shift" $REPO/scripts/estimate-cost.sh --tokens 50000 --model flash --window off-peak --json
```
Must produce same output as pre-migration baseline.

- [ ] **Step 3: SKILL.md cleanliness**

```bash
grep -c '~/.claude/' $REPO/SKILL.md
```
Expected: 0

- [ ] **Step 4: All symlinks valid**

```bash
test -f $REPO/.qoder/skills/night-shift/SKILL.md
test -f ~/.codex/skills/night-shift/SKILL.md
test -d $REPO/.agents/skills/night-shift/scripts
```
All must pass.

- [ ] **Step 5: Final status check**

```bash
cd $REPO && git status
```
Expected: only the files we intentionally modified/created, no stray changes.
