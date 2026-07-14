# night-shift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code skill that schedules agent jobs during off-peak DeepSeek pricing windows, routes subagents to cost-optimal models, and supports L2→L3 autonomy progression.

**Architecture:** Three shell scripts for deterministic ops (time check, cost estimate, queue parse) + one SKILL.md that teaches Claude the scheduling/routing protocols + config/state files at `~/.claude/night-shift/`. CronCreate fires daily at 18:05 Beijing; ScheduleWakeup paces jobs.

**Tech Stack:** Bash (scripts), Markdown (SKILL.md, queue files, reference docs), JSON (config, state), Claude Code Workflow.js primitives (agent, pipeline, parallel).

---

## File Map

```
~/.claude/night-shift/                    ← Config & runtime state (created by init)
  config.json                             ← User-editable thresholds
  state.json                              ← Machine-facing runtime state (auto-managed)

~/.claude/skills/night-shift/            ← Skill directory (source)
  SKILL.md                               ← Main skill: ~180 lines, all logic
  references/
    pricing.md                           ← Pricing tables reference
  scripts/
    check-window.sh                      ← Time window detection (~40 lines)
    estimate-cost.sh                     ← Token→CNY estimator (~50 lines)
    parse-queue.sh                       ← NIGHTSHIFT.md→JSON parser (~80 lines)
```

---

## Task 1: Create Directory Structure and Default Config

**Files:**
- Create: `~/.claude/skills/night-shift/` (directory)
- Create: `~/.claude/skills/night-shift/references/` (directory)
- Create: `~/.claude/skills/night-shift/scripts/` (directory)
- Create: `~/.claude/night-shift/config.json`

- [ ] **Step 1: Create all directories**

```bash
mkdir -p ~/.claude/skills/night-shift/references \
         ~/.claude/skills/night-shift/scripts \
         ~/.claude/night-shift
```

- [ ] **Step 2: Write default config.json**

```bash
cat > ~/.claude/night-shift/config.json << 'CONFEOF'
{
  "autonomy": "L2",
  "budget": {
    "daily_max_tokens": 2000000,
    "soft_cap": false
  },
  "thresholds": {
    "peak_dispatch_max_tokens": 200000,
    "peak_force_flash": true,
    "retry_max": 3,
    "escalate_after_failures": 3
  },
  "projects": {
    "discover": true,
    "paths": [],
    "blacklist": []
  },
  "schedule": {
    "off_peak_wakeup": "18:05",
    "inter_job_pause_minutes": 5
  }
}
CONFEOF
```

- [ ] **Step 3: Verify**

```bash
cat ~/.claude/night-shift/config.json | python3 -m json.tool > /dev/null && echo "OK: valid JSON"
ls ~/.claude/skills/night-shift/{references,scripts}/
```

Expected:
```
OK: valid JSON
references:
scripts:
```

---

## Task 2: Write check-window.sh

**Files:**
- Create: `~/.claude/skills/night-shift/scripts/check-window.sh`

- [ ] **Step 1: Write the script**

```bash
cat > ~/.claude/skills/night-shift/scripts/check-window.sh << 'SCRIPTEOF'
#!/usr/bin/env bash
# check-window.sh — Returns current Beijing time pricing window
#
# Output: window=<peak|off-peak> minutes_remaining=<int> next_transition=<HH:MM>
# Options:
#   --simulate peak    Pretend current time is in peak window
#   --simulate off-peak  Pretend current time is in off-peak window
#   --json             Output as JSON

set -euo pipefail

SIMULATE=""
OUTPUT_JSON=false

for arg in "$@"; do
  case "$arg" in
    --simulate) SIMULATE="${2:-}"; shift ;;
    --json) OUTPUT_JSON=true ;;
  esac
done

# Get current Beijing time (UTC+8)
if [[ -n "$SIMULATE" ]]; then
  if [[ "$SIMULATE" == "peak" ]]; then
    # Simulate: 10:00 Beijing (peak)
    HOUR=10 MINUTE=0
  else
    # Simulate: 22:00 Beijing (off-peak)
    HOUR=22 MINUTE=0
  fi
else
  HOUR=$(TZ='Asia/Shanghai' date +%H)
  MINUTE=$(TZ='Asia/Shanghai' date +%M)
  # Remove leading zeros for arithmetic
  HOUR=$((10#$HOUR))
  MINUTE=$((10#$MINUTE))
fi

# Peak windows: 09:00-12:00 and 14:00-18:00 Beijing time
is_peak() {
  local h=$1 m=$2
  local total=$((h * 60 + m))
  local peak1_start=$((9 * 60))     # 09:00
  local peak1_end=$((12 * 60))      # 12:00
  local peak2_start=$((14 * 60))    # 14:00
  local peak2_end=$((18 * 60))      # 18:00

  if (( total >= peak1_start && total < peak1_end )); then return 0; fi
  if (( total >= peak2_start && total < peak2_end )); then return 0; fi
  return 1
}

# Calculate minutes until next transition
calc_remaining() {
  local h=$1 m=$2
  local total=$((h * 60 + m))

  local transitions=(
    $((9 * 60))    # off-peak → peak (morning)
    $((12 * 60))   # peak → off-peak (lunch)
    $((14 * 60))   # off-peak → peak (afternoon)
    $((18 * 60))   # peak → off-peak (evening)
  )

  local next=9999
  for t in "${transitions[@]}"; do
    if (( t > total && t < next )); then
      next=$t
    fi
  done

  # Wrap around midnight
  if (( next == 9999 )); then
    next=$((9 * 60))
  fi

  echo $((next - total))
}

if is_peak "$HOUR" "$MINUTE"; then
  WINDOW="peak"
  NEXT_WINDOW="off-peak"
else
  WINDOW="off-peak"
  NEXT_WINDOW="peak"
fi

MINUTES_REMAINING=$(calc_remaining "$HOUR" "$MINUTE")

# Format next_transition
NEXT_HOUR=$(( (HOUR * 60 + MINUTE + MINUTES_REMAINING) / 60 % 24 ))
NEXT_MIN=$(( (HOUR * 60 + MINUTE + MINUTES_REMAINING) % 60 ))
NEXT_TRANSITION=$(printf "%02d:%02d CST" "$NEXT_HOUR" "$NEXT_MIN")

if $OUTPUT_JSON; then
  cat << JSONEOF
{"window":"$WINDOW","minutes_remaining":$MINUTES_REMAINING,"next_transition":"$NEXT_TRANSITION","next_window":"$NEXT_WINDOW"}
JSONEOF
else
  echo "window=$WINDOW minutes_remaining=$MINUTES_REMAINING next_transition=$NEXT_TRANSITION next_window=$NEXT_WINDOW"
fi
SCRIPTEOF

chmod +x ~/.claude/skills/night-shift/scripts/check-window.sh
```

- [ ] **Step 2: Test — real time**

```bash
~/.claude/skills/night-shift/scripts/check-window.sh
```

Expected: Prints current window (varies by time of day). Example output: `window=off-peak minutes_remaining=543 next_transition=09:00 CST next_window=peak`

- [ ] **Step 3: Test — simulate peak**

```bash
~/.claude/skills/night-shift/scripts/check-window.sh --simulate peak
```

Expected: `window=peak minutes_remaining=120 next_transition=12:00 CST next_window=off-peak`

- [ ] **Step 4: Test — simulate off-peak**

```bash
~/.claude/skills/night-shift/scripts/check-window.sh --simulate off-peak
```

Expected: `window=off-peak minutes_remaining=660 next_transition=09:00 CST next_window=peak`  
(22:00 → 09:00 next day is 11 hours = 660 minutes)

- [ ] **Step 5: Test — JSON output**

```bash
~/.claude/skills/night-shift/scripts/check-window.sh --simulate peak --json | python3 -m json.tool
```

Expected: Valid JSON with `window: "peak"`, `minutes_remaining: 120`, `next_window: "off-peak"`

---

## Task 3: Write estimate-cost.sh

**Files:**
- Create: `~/.claude/skills/night-shift/scripts/estimate-cost.sh`

- [ ] **Step 1: Write the script**

```bash
cat > ~/.claude/skills/night-shift/scripts/estimate-cost.sh << 'SCRIPTEOF'
#!/usr/bin/env bash
# estimate-cost.sh — Estimate DeepSeek API cost for a job
#
# Usage: estimate-cost.sh --tokens <N> --model <pro|flash> --window <peak|off-peak> [--json]
#   --tokens N            Estimated total tokens (input + output)
#   --model pro|flash     DeepSeek model variant
#   --window peak|off-peak  Current pricing window
#   --json                Output as JSON

set -euo pipefail

TOKENS=""
MODEL=""
WINDOW=""
OUTPUT_JSON=false
INPUT_RATIO=0.5   # Assume 50% input, 50% output tokens

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tokens) TOKENS="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --window) WINDOW="$2"; shift 2 ;;
    --input-ratio) INPUT_RATIO="$2"; shift 2 ;;
    --json) OUTPUT_JSON=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$TOKENS" || -z "$MODEL" || -z "$WINDOW" ]]; then
  echo "Usage: estimate-cost.sh --tokens <N> --model <pro|flash> --window <peak|off-peak> [--json]"
  exit 1
fi

# Pricing tables in CNY per million tokens
# DeepSeek-V4-Pro
PRO_OFF_OUTPUT=6
PRO_PEAK_OUTPUT=12
PRO_OFF_INPUT_MISS=3
PRO_PEAK_INPUT_MISS=6
PRO_OFF_INPUT_HIT=0.025
PRO_PEAK_INPUT_HIT=0.05

# DeepSeek-V4-Flash
FLASH_OFF_OUTPUT=2
FLASH_PEAK_OUTPUT=4
FLASH_OFF_INPUT_MISS=1
FLASH_PEAK_INPUT_MISS=2
FLASH_OFF_INPUT_HIT=0.02
FLASH_PEAK_INPUT_HIT=0.04

MULT=1
if [[ "$WINDOW" == "peak" ]]; then
  MULT=2
fi

if [[ "$MODEL" == "pro" ]]; then
  OUTPUT_RATE=$(awk "BEGIN {printf \"%.2f\", 6 * $MULT}")
  INPUT_RATE=$(awk "BEGIN {printf \"%.2f\", 3 * $MULT}")
  CACHE_HIT_RATE=$(awk "BEGIN {printf \"%.3f\", 0.025 * $MULT}")
elif [[ "$MODEL" == "flash" ]]; then
  OUTPUT_RATE=$(awk "BEGIN {printf \"%.2f\", 2 * $MULT}")
  INPUT_RATE=$(awk "BEGIN {printf \"%.2f\", 1 * $MULT}")
  CACHE_HIT_RATE=$(awk "BEGIN {printf \"%.3f\", 0.02 * $MULT}")
else
  echo "Unknown model: $MODEL (use pro or flash)"
  exit 1
fi

TOKENS_M=$(awk "BEGIN {printf \"%.6f\", $TOKENS / 1000000}")
INPUT_TOKENS_M=$(awk "BEGIN {printf \"%.6f\", $TOKENS_M * $INPUT_RATIO}")
OUTPUT_TOKENS_M=$(awk "BEGIN {printf \"%.6f\", $TOKENS_M * (1 - $INPUT_RATIO)}")

# Assume cache miss for worst-case estimate (most input is fresh context)
INPUT_COST=$(awk "BEGIN {printf \"%.4f\", $INPUT_TOKENS_M * $INPUT_RATE}")
OUTPUT_COST=$(awk "BEGIN {printf \"%.4f\", $OUTPUT_TOKENS_M * $OUTPUT_RATE}")
TOTAL_COST=$(awk "BEGIN {printf \"%.4f\", $INPUT_COST + $OUTPUT_COST}")

# Compare with off-peak
if [[ "$WINDOW" == "peak" ]]; then
  OFFPEAK_INPUT_COST=$(awk "BEGIN {printf \"%.4f\", $INPUT_TOKENS_M * ($INPUT_RATE / 2)}")
  OFFPEAK_OUTPUT_COST=$(awk "BEGIN {printf \"%.4f\", $OUTPUT_TOKENS_M * ($OUTPUT_RATE / 2)}")
  OFFPEAK_TOTAL=$(awk "BEGIN {printf \"%.4f\", $OFFPEAK_INPUT_COST + $OFFPEAK_OUTPUT_COST}")
  SAVINGS=$(awk "BEGIN {printf \"%.4f\", $TOTAL_COST - $OFFPEAK_TOTAL}")
fi

if $OUTPUT_JSON; then
  cat << JSONEOF
{
  "model": "$MODEL",
  "window": "$WINDOW",
  "tokens": $TOKENS,
  "tokens_millions": $(awk "BEGIN {printf \"%.2f\", $TOKENS_M}"),
  "input_cost_cny": $INPUT_COST,
  "output_cost_cny": $OUTPUT_COST,
  "total_cost_cny": $TOTAL_COST
}
JSONEOF
  if [[ "$WINDOW" == "peak" ]]; then
    echo "off-peak comparison:"
    echo "  off-peak would be: ${OFFPEAK_TOTAL} CNY (save ${SAVINGS} CNY)"
  fi
else
  echo "Model: DeepSeek-V4-$(echo $MODEL | tr '[:lower:]' '[:upper:]')"
  echo "Window: $WINDOW"
  echo "Tokens: $TOKENS (~$(awk "BEGIN {printf \"%.2f\", $TOKENS_M}")M)"
  echo "Estimated input cost:  ${INPUT_COST} CNY"
  echo "Estimated output cost: ${OUTPUT_COST} CNY"
  echo "Estimated total:       ${TOTAL_COST} CNY"
  if [[ "$WINDOW" == "peak" ]]; then
    echo "Off-peak would be:     ${OFFPEAK_TOTAL} CNY (premium: ${SAVINGS} CNY)"
  fi
fi
SCRIPTEOF

chmod +x ~/.claude/skills/night-shift/scripts/estimate-cost.sh
```

- [ ] **Step 2: Test — Pro off-peak 1M tokens**

```bash
~/.claude/skills/night-shift/scripts/estimate-cost.sh --tokens 1000000 --model pro --window off-peak
```

Expected: ~4.50 CNY (500k input × 3 CNY/M + 500k output × 6 CNY/M)

- [ ] **Step 3: Test — Pro peak 1M tokens**

```bash
~/.claude/skills/night-shift/scripts/estimate-cost.sh --tokens 1000000 --model pro --window peak
```

Expected: ~9.00 CNY (2× off-peak). Should show premium warning.

- [ ] **Step 4: Test — Flash off-peak 500k tokens**

```bash
~/.claude/skills/night-shift/scripts/estimate-cost.sh --tokens 500000 --model flash --window off-peak
```

Expected: ~0.75 CNY (250k input × 1 CNY/M + 250k output × 2 CNY/M)

- [ ] **Step 5: Test — JSON output**

```bash
~/.claude/skills/night-shift/scripts/estimate-cost.sh --tokens 100000 --model flash --window off-peak --json | python3 -m json.tool
```

Expected: Valid JSON, `total_cost_cny` ~0.15

---

## Task 4: Write parse-queue.sh

**Files:**
- Create: `~/.claude/skills/night-shift/scripts/parse-queue.sh`

- [ ] **Step 1: Write the script**

```bash
cat > ~/.claude/skills/night-shift/scripts/parse-queue.sh << 'SCRIPTEOF'
#!/usr/bin/env bash
# parse-queue.sh — Parse NIGHTSHIFT.md files and output aggregated state JSON
#
# Usage: parse-queue.sh [--project <path>] [--all]
#   --project <path>  Parse a specific NIGHTSHIFT.md file
#   --all             Scan all discovered projects and merge
#   --json            Output as JSON (default)

set -euo pipefail

OUTPUT_JSON=true
TARGET=""
MODE="all"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) TARGET="$2"; MODE="project"; shift 2 ;;
    --all) MODE="all"; shift ;;
    *) shift ;;
  esac
done

# Parse a single NIGHTSHIFT.md file into JSON job entries
parse_file() {
  local file="$1"
  local project
  project=$(basename "$(dirname "$(realpath "$file")")")

  if [[ ! -f "$file" ]]; then
    echo "[]"
    return
  fi

  local in_section=""
  local jobs="["
  local first=true
  local job_json=""
  local job_desc=""
  local capturing_prompt=false
  local prompt_text=""

  while IFS= read -r line; do
    # Detect section headers
    if echo "$line" | grep -q '^## Pending'; then
      in_section="pending"
      continue
    elif echo "$line" | grep -q '^## Done'; then
      in_section="done"
      continue
    elif echo "$line" | grep -q '^## Failed'; then
      in_section="failed"
      continue
    elif echo "$line" | grep -q '^## '; then
      in_section=""
      continue
    fi

    if [[ "$in_section" != "pending" ]]; then
      continue
    fi

    # Detect job start: "- [ ] **job-id** — Description."
    if echo "$line" | grep -qE '^- \[ \] \*\*[^*]+\*\*'; then
      # Save previous job if any
      if [[ -n "$job_json" ]]; then
        if $first; then first=false; else jobs+=","; fi
        # Close prompt if capturing
        if $capturing_prompt; then
          prompt_text=$(echo "$prompt_text" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo '""')
          job_json+="\"prompt\": $prompt_text}"
        fi
        jobs+="$job_json"
      fi

      local job_id
      job_id=$(echo "$line" | sed -E 's/^- \[ \] \*\*([^*]+)\*\*.*/\1/')
      local desc
      desc=$(echo "$line" | sed -E 's/^- \[ \] \*\*[^*]+\*\* — //' | sed 's/\.$//')
      job_json="{\"id\":\"$job_id\",\"project\":\"$project\",\"description\":\"$desc\",\"status\":\"pending\""
      job_desc=""
      capturing_prompt=false
      prompt_text=""
      continue
    fi

    # Parse metadata fields within a job entry
    if [[ -n "$job_json" ]]; then
      if echo "$line" | grep -qE '^\s+submitted:'; then
        local val
        val=$(echo "$line" | sed -E 's/^\s+submitted:\s*//')
        job_json+=",\"submitted\":\"$val\""
      elif echo "$line" | grep -qE '^\s+type:'; then
        local val
        val=$(echo "$line" | sed -E 's/^\s+type:\s*//')
        job_json+=",\"type\":\"$val\""
      elif echo "$line" | grep -qE '^\s+priority:'; then
        local val
        val=$(echo "$line" | sed -E 's/^\s+priority:\s*//')
        job_json+=",\"priority\":\"$val\""
      elif echo "$line" | grep -qE '^\s+estimated-tokens:'; then
        local val
        val=$(echo "$line" | sed -E 's/^\s+estimated-tokens:\s*~?//' | sed 's/[^0-9]//g')
        job_json+=",\"estimated_tokens\":$val"
      elif echo "$line" | grep -qE '^\s+model-hint:'; then
        local val
        val=$(echo "$line" | sed -E 's/^\s+model-hint:\s*//')
        job_json+=",\"model_hint\":\"$val\""
      elif echo "$line" | grep -qE '^\s+prompt: \|'; then
        capturing_prompt=true
        prompt_text=""
      elif $capturing_prompt && echo "$line" | grep -qE '^\s{6,}'; then
        prompt_text+="$(echo "$line" | sed 's/^\s\{6,\}//')
"
      elif $capturing_prompt && ! echo "$line" | grep -qE '^\s{6,}'; then
        capturing_prompt=false
      fi
    fi
  done < "$file"

  # Save final job
  if [[ -n "$job_json" ]]; then
    if $first; then first=false; else jobs+=","; fi
    if $capturing_prompt; then
      prompt_text=$(echo "$prompt_text" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || echo '""')
      job_json+=",\"prompt\": $prompt_text}"
    fi
    jobs+="$job_json"
  fi

  jobs+="]"
  echo "$jobs"
}

find_project_queues() {
  local queues=()

  # Scan ~/.claude/projects/ for NIGHTSHIFT.md files
  if [[ -d "$HOME/.claude/projects" ]]; then
    for q in "$HOME/.claude/projects"/*/NIGHTSHIFT.md; do
      if [[ -f "$q" ]]; then
        queues+=("$q")
      fi
    done
  fi

  # Add explicit paths from config
  if [[ -f "$HOME/.claude/night-shift/config.json" ]]; then
    local extra_paths
    extra_paths=$(python3 -c "
import json, os
try:
    with open(os.path.expanduser('~/.claude/night-shift/config.json')) as f:
        cfg = json.load(f)
    for p in cfg.get('projects',{}).get('paths',[]):
        q = os.path.join(os.path.expanduser(p), 'NIGHTSHIFT.md')
        if os.path.exists(q):
            print(q)
except: pass
" 2>/dev/null)
    if [[ -n "$extra_paths" ]]; then
      while IFS= read -r q; do
        queues+=("$q")
      done <<< "$extra_paths"
    fi
  fi

  echo "${queues[@]}"
}

if [[ "$MODE" == "project" && -n "$TARGET" ]]; then
  parse_file "$TARGET"
else
  # Aggregate all project queues
  QUEUES=($(find_project_queues))

  echo -n '{"last_scan":"'"$(TZ='Asia/Shanghai' date -Iseconds)"'","projects":{'
  local first_proj=true
  for q in "${QUEUES[@]}"; do
    local proj
    proj=$(basename "$(dirname "$(realpath "$q")")")
    if $first_proj; then first_proj=false; else echo -n ','; fi
    echo -n "\"$proj\":$(parse_file "$q")"
  done
  echo '}}'
fi
SCRIPTEOF

chmod +x ~/.claude/skills/night-shift/scripts/parse-queue.sh
```

- [ ] **Step 2: Create a test NIGHTSHIFT.md fixture**

```bash
mkdir -p /tmp/night-shift-test/fake-project
cat > /tmp/night-shift-test/fake-project/NIGHTSHIFT.md << 'FIXEOF'
# Night Shift Queue — fake-project

Last dispatch: 2026-06-30 18:10 CST (+8)

## Pending

- [ ] **train-ablation** — Run full ablation study.
  submitted: 2026-06-30
  type: ml-training
  priority: high
  estimated-tokens: ~2M
  model-hint: pro
  prompt: |
    Run the ablation study script at scripts/ablate.sh.
    Check results against baseline.csv and report findings.

- [ ] **lint-fix** — Fix all lint warnings.
  submitted: 2026-06-29
  type: lint
  priority: low
  estimated-tokens: ~100k
  model-hint: auto

## Done

- [x] **old-job** — done 2026-06-28 | 1 attempt | ~50k tokens

## Failed

- [x] **broken-job** — failed 2026-06-27 | 3 attempts exhausted
FIXEOF
```

- [ ] **Step 3: Test parse — single project**

```bash
~/.claude/skills/night-shift/scripts/parse-queue.sh --project /tmp/night-shift-test/fake-project/NIGHTSHIFT.md | python3 -m json.tool
```

Expected: JSON array with 2 pending jobs (`train-ablation` and `lint-fix`), each with correct parsed fields. `train-ablation` should have `model_hint: "pro"` and `estimated_tokens: 2` (the M suffix stripped in the parser... actually let me note: the parser strips non-numeric chars, so ~2M → 2. We should fix that or handle it.)

Wait — the estimate-cost.sh uses actual token counts, not millions. The parser needs to handle this. Let me fix: `estimated-tokens: ~2M` → `estimated_tokens: 2000000`. I should adjust the parser.

Actually, let me leave the parser as-is for now and note this in the test. The parser removes non-numeric characters, so `~2M` → `2`. We should document that estimated-tokens must be in raw token count (e.g., `2000000` not `2M`). Or better, let me fix the spec/parser to handle `M` and `K` suffixes.

Let me update the parser to handle this. I'll adjust in the plan.

```bash
~/.claude/skills/night-shift/scripts/parse-queue.sh --project /tmp/night-shift-test/fake-project/NIGHTSHIFT.md | python3 -m json.tool
```

Expected: 2 jobs in JSON array. `train-ablation` has `model_hint: "pro"`, `priority: "high"`, `type: "ml-training"`. `lint-fix` has `model_hint: "auto"`, `priority: "low"`.

- [ ] **Step 4: Test parse — aggregate mode (--all)**

```bash
# Temporarily symlink the test project into ~/.claude/projects/ for discovery
mkdir -p ~/.claude/projects
ln -sf /tmp/night-shift-test/fake-project ~/.claude/projects/fake-project 2>/dev/null || true
~/.claude/skills/night-shift/scripts/parse-queue.sh --all | python3 -m json.tool
```

Expected: JSON with `projects.fake-project` array containing 2 pending jobs.

---

## Task 5: Write references/pricing.md

**Files:**
- Create: `~/.claude/skills/night-shift/references/pricing.md`

- [ ] **Step 1: Write the pricing reference**

```bash
cat > ~/.claude/skills/night-shift/references/pricing.md << 'REFEOF'
# DeepSeek V4 Pricing (Effective July 2026)

Beijing time (UTC+8). Peak: 09:00–12:00 and 14:00–18:00. Off-peak: all other times.

Peak prices are 2× off-peak.

## DeepSeek-V4-Pro

| Billing Item         | Off-peak (CNY/M tokens) | Peak (CNY/M tokens) |
|----------------------|------------------------|---------------------|
| Input (cache hit)    | 0.025                  | 0.05                |
| Input (cache miss)   | 3                      | 6                   |
| Output               | 6                      | 12                  |

## DeepSeek-V4-Flash

| Billing Item         | Off-peak (CNY/M tokens) | Peak (CNY/M tokens) |
|----------------------|------------------------|---------------------|
| Input (cache hit)    | 0.02                   | 0.04                |
| Input (cache miss)   | 1                      | 2                   |
| Output               | 2                      | 4                   |

## Model Routing Summary

| Window   | Job Hint | Plan/Reason Role | Execute/Verify Role |
|----------|----------|-----------------|---------------------|
| Off-peak | auto     | Pro             | Pro                 |
| Peak     | auto     | Pro (L2 gate)   | Flash               |
| Peak     | pro      | Pro             | Pro                 |
| Any      | flash    | Flash           | Flash               |
REFEOF
```

- [ ] **Step 2: Verify**

```bash
wc -l ~/.claude/skills/night-shift/references/pricing.md
```

Expected: ~35 lines.

---

## Task 6: Write SKILL.md

**Files:**
- Create: `~/.claude/skills/night-shift/SKILL.md`

- [ ] **Step 1: Write the skill file**

```bash
cat > ~/.claude/skills/night-shift/SKILL.md << 'SKILLEOF'
---
name: night-shift
description: >
  Pricing-aware job scheduler for DeepSeek models. Organizes project-level job queues,
  dispatches subagents during off-peak pricing windows, and routes work to cost-optimal
  models (Pro vs Flash) based on time of day. TRIGGERS: /night-shift commands, "night-shift",
  "run this off-peak", "schedule this job", "queue this for later", "dispatch during cheap hours",
  "what's in the night shift queue", "night shift status", asking about job queue or pricing-aware
  scheduling. Use when the user wants to submit, check, or manage queued agent jobs.
argument-hint: "<command> [args...]"
user-invocable: true
version: "1.0.0"
---

# night-shift

Pricing-aware job scheduler for DeepSeek V4 models. Submits jobs to project queues,
dispatches them during off-peak pricing windows, and routes subagents to the cheapest
appropriate model.

## Quick Start

```
/night-shift:submit my-project "Fix all lint warnings in src/"
/night-shift:status
/night-shift:run train-ablation    # force immediate dispatch
```

## Pricing Windows (Beijing Time UTC+8)

| Window   | Hours                                    | Pro Output | Flash Output |
|----------|------------------------------------------|------------|--------------|
| 🔴 Peak  | 09:00–12:00, 14:00–18:00                | 12 CNY/M   | 4 CNY/M      |
| 🟢 Off-peak | 00:00–08:59, 12:00–13:59, 18:00–23:59 | 6 CNY/M    | 2 CNY/M      |

Full pricing tables: see `references/pricing.md`.

Before making any dispatch decision, run `scripts/check-window.sh` to get the
current window. Before dispatching any job, run `scripts/estimate-cost.sh` to
show the user the estimated cost.

## Tool Loading (IMPORTANT)

On first use in a session, load the deferred scheduling tools:

```
ToolSearch query: "select:CronCreate,CronDelete,CronList,ScheduleWakeup"
```

These tools are required for cron scheduling and inter-job pacing. Do this before
any schedule operation.

## Interactive Commands

### /night-shift:submit <project> <description>

Append a job to the project's `NIGHTSHIFT.md`. The description can be a short
one-liner or a multi-line prompt.

Process:
1. Locate the project's `NIGHTSHIFT.md`:
   - If the project is at `~/<project>/`, write to `~/<project>/NIGHTSHIFT.md`
   - If under `~/.claude/projects/<project>/`, write there
   - If neither exists, ask the user for the project path
2. If `NIGHTSHIFT.md` doesn't exist, create it with the header template:
```markdown
# Night Shift Queue — <project>

Last dispatch: (never)

## Pending

## Done (7-day auto-prune)

## Failed (needs human)
```
3. Append the job to the `## Pending` section:
```markdown
- [ ] **<kebab-case-job-id>** — <one-line description>.
  submitted: YYYY-MM-DD
  type: ml-training | benchmark | fix | refactor | lint | custom
  priority: high | normal | low
  estimated-tokens: ~<N>
  model-hint: auto | pro | flash
  prompt: |
    <multi-line prompt for the agent>
```
4. Derive the job-id from the description (kebab-case, max 40 chars).
5. Guess `type` and `priority` from the description. Default: type=custom, priority=normal.
6. Default `model-hint: auto` unless the user specifies otherwise.
7. Confirm with the user: "Added **<job-id>** to <project> queue. [N] jobs pending."

### /night-shift:status

Show all queues, current pricing window, today's estimated spend, and any escalated jobs.

Process:
1. Run `scripts/check-window.sh` to get the current window.
2. Run `scripts/parse-queue.sh --all` to aggregate all project queues.
3. Read `~/.claude/night-shift/config.json` for budget info.
4. Read `~/.claude/night-shift/state.json` for today's spend (if exists).
5. Display a summary table:

```
🕐 Window: off-peak (next peak at 09:00 CST, 4h 32m remaining)

| Project      | Pending | Done Today | Failed |
|-------------|---------|------------|--------|
| MARLIN       | 3       | 1          | 0      |
| skills-repo  | 1       | 0          | 1      |

Today's spend: ~1.2M / 5M tokens (24%)
Next dispatch: 18:05 CST (CronCreate active)
```

### /night-shift:run [job-id]

Force immediate dispatch of a specific job, bypassing the window check.

Process:
1. Run `scripts/check-window.sh`. Show the window and cost estimate.
2. If peak: warn about 2× pricing, show cost difference.
3. At L2: ask user to confirm before dispatching during peak.
4. At L3: dispatch if under `peak_dispatch_max_tokens` threshold, else ask.
5. Follow the dispatch protocol (see below).
6. Update the job status in `NIGHTSHIFT.md`.

### /night-shift:hold <job-id>

Move a pending job to held state (add `<!-- held: <reason> -->` comment above it).

### /night-shift:retry <job-id>

Reset a failed job back to pending. Reset its attempt counter.

### /night-shift:config

Display the current config. If the user passes `--set key=value`, update config.json.
Example: `/night-shift:config --set autonomy=L3`

## Dispatch Protocol

When dispatching a job (whether from cron or `/night-shift:run`):

### 1. Pre-flight Checks

Run `scripts/check-window.sh --json` and `scripts/estimate-cost.sh --tokens <N> --model <M> --window <W> --json`.

Check budget:
- Read `state.json` for `spent_today`.
- If `spent_today + estimate > daily_max_tokens`:
  - `soft_cap: false` → hold job, report budget exhausted.
  - `soft_cap: true` → dispatch but warn.

### 2. Model Selection

Apply the routing matrix:

| Window   | model-hint | Role            | Model |
|----------|-----------|-----------------|-------|
| Off-peak | auto      | Any             | Pro   |
| Off-peak | pro       | Any             | Pro   |
| Off-peak | flash     | Any             | Flash |
| Peak     | auto      | Plan/Reason     | Pro   |
| Peak     | auto      | Execute/Verify  | Flash |
| Peak     | pro       | Any             | Pro   |
| Peak     | flash     | Any             | Flash |

At L2, if dispatching a Pro job during peak: show cost and ask user to confirm.
At L3, if dispatching a Pro job during peak: check against `peak_dispatch_max_tokens`.

### 3. Execution

Use the Workflow tool with a script that:
1. Opens a worktree (`isolation: "worktree"`)
2. Spawns an implementer agent with the job's prompt, using the selected model
3. Spawns a verifier agent (always Flash for cost efficiency) to check the result
4. On success: update `NIGHTSHIFT.md` → move job to Done
5. On failure: increment attempt counter. If < retry_max, reset to pending. If exhausted, move to Failed.

Workflow script template for each job:
```javascript
export const meta = {
  name: 'night-shift-dispatch',
  description: 'Dispatch a queued job with pricing-aware model selection',
  phases: [{ title: 'Implement' }, { title: 'Verify' }],
}

phase('Implement')
const result = await agent(args.prompt, {
  model: args.model,        // determined by routing matrix
  isolation: 'worktree',
  schema: {
    type: 'object',
    properties: {
      success: { type: 'boolean' },
      summary: { type: 'string' },
      artifacts: { type: 'array', items: { type: 'string' } },
    },
    required: ['success', 'summary'],
  },
})

phase('Verify')
const verdict = await agent(
  `Verify this work. The implementer was asked: "${args.prompt}".\n\n` +
  `Result summary: ${result.summary}\n` +
  `Artifacts: ${(result.artifacts || []).join(', ')}\n\n` +
  `Check: did it do what was asked? Are there obvious bugs? ` +
  `Respond with { pass: boolean, issues: string[] }.`,
  {
    model: 'flash',
    schema: {
      type: 'object',
      properties: {
        pass: { type: 'boolean' },
        issues: { type: 'array', items: { type: 'string' } },
      },
      required: ['pass'],
    },
  }
)

return { success: result.success && verdict.pass, summary: result.summary, issues: verdict.issues }
```

### 4. Post-Dispatch

Update the job in `NIGHTSHIFT.md`:
```
- [x] **job-id** — done YYYY-MM-DD | 1 attempt | ~N tokens
```

Update `state.json`: increment `spent_today` by estimated tokens, update `last_dispatch`.

If more pending jobs remain, set `ScheduleWakeup` with `inter_job_pause_minutes` delay
to process the next one.

## Scheduled Dispatch (Cron)

When fired by CronCreate, the skill runs autonomously:

1. Run `scripts/check-window.sh --json`.
2. If off-peak: proceed to dispatch cycle.
3. If peak with <30 min until off-peak: set ScheduleWakeup for when off-peak starts.
4. If peak with >30 min until off-peak: exit (don't burn tokens waiting).
5. Run `scripts/parse-queue.sh --all`.
6. Sort pending jobs by priority (high > normal > low), then by submission date (FIFO).
7. For each job: run pre-flight checks → if budget ok → dispatch (see Dispatch Protocol).
8. One job per project at a time. Cross-project parallel dispatch OK via Workflow.
9. After all jobs dispatched or budget exhausted: update state, prune Done >7 days.

### Initial Cron Setup

On first run or when user asks to "start night-shift scheduling":

1. Load deferred tools: `ToolSearch query: "select:CronCreate"`
2. Read `config.json` for `schedule.off_peak_wakeup` (default: "18:05").
3. Parse the wakeup time into a cron expression in Beijing time:
   - "18:05" → `"5 18 * * *"` (fires daily at 18:05 Beijing)

4. Create the cron job:
```
CronCreate({
  cron: "5 18 * * *",
  prompt: "Run the night-shift skill: check window, scan all project NIGHTSHIFT.md files, dispatch pending jobs that fit within budget during off-peak. Update queue status after each job.",
  recurring: true,
  durable: true
})
```

5. Confirm: "night-shift scheduled daily at 18:05 Beijing (off-peak). Use `/night-shift:status` to check the queue."

Optional supplementary crons:
- `"5 12 * * *"` for lunch gap dispatch
- `"5 0 * * *"` for overnight dispatch

### Schedule Management

- `/night-shift:config --set schedule.off_peak_wakeup=22:00` → delete old cron, create new one
- `/night-shift:status` shows active cron jobs from CronList

## Autonomy Levels

Behavior changes based on `config.json → autonomy`:

### L2 (Default — Assisted)

| Situation | Behavior |
|-----------|----------|
| Peak dispatch (Pro) | Show cost estimate, ask user to confirm |
| Peak dispatch (Flash, <200k tokens) | Auto-dispatch |
| Budget exhausted | Hold job, notify user |
| Failed job | Escalate to human immediately |
| New project queue detected | Ask user to review before first dispatch |
| model-hint: pro on peak | Warn, confirm |

### L3 (Unattended)

| Situation | Behavior |
|-----------|----------|
| Peak dispatch (Pro) | Auto if <peak_dispatch_max_tokens; hold otherwise |
| Peak dispatch (Flash) | Auto-dispatch (always cheap) |
| Budget exhausted | Soft-cap: throttle, log warning. Hard-cap: hold. |
| Failed job | Auto-retry up to retry_max, then escalate |
| New project queue | Auto-discover, trust queue |
| model-hint: pro | Honored silently |

### Upgrading to L3

User sets `autonomy: "L3"` in config.json. The skill applies L3 rules immediately.
Recommendation: run L2 for at least 1 week, review escalated jobs, then upgrade.

## State File

`~/.claude/night-shift/state.json` — machine-facing, not human-edited:

```json
{
  "last_scan": "2026-06-30T18:05:00+08:00",
  "last_dispatch": "2026-06-30T18:07:00+08:00",
  "spent_today": 1200000,
  "jobs_dispatched_today": 2,
  "active_worktrees": {
    "marlin-fix-attention": "/tmp/night-shift-wt-abc123"
  }
}
```

Reset `spent_today` and `jobs_dispatched_today` at midnight Beijing time.

## Scripts Reference

| Script | Purpose | Deterministic |
|--------|---------|---------------|
| `scripts/check-window.sh` | Current Beijing pricing window | Yes |
| `scripts/estimate-cost.sh` | Token → CNY estimate | Yes |
| `scripts/parse-queue.sh` | NIGHTSHIFT.md → JSON | Yes |

Always use scripts for deterministic operations. Don't waste tokens on time math or cost arithmetic.
SKILLEOF
```

- [ ] **Step 2: Verify SKILL.md has valid YAML frontmatter**

```bash
head -10 ~/.claude/skills/night-shift/SKILL.md
```

Expected: `---` on line 1, `name: night-shift` on line 2, etc.

- [ ] **Step 3: Verify skill is discoverable by Claude Code**

```bash
ls -la ~/.claude/skills/night-shift/SKILL.md
```

Expected: File exists, non-zero size.

---

## Task 7: Fix parse-queue.sh Token Suffix Handling

**Files:**
- Modify: `~/.claude/skills/night-shift/scripts/parse-queue.sh`

- [ ] **Step 1: Update the estimated-tokens parser to handle K/M suffixes**

Edit `parse-queue.sh`. Find the line:
```bash
val=$(echo "$line" | sed -E 's/^\s+estimated-tokens:\s*~?//' | sed 's/[^0-9]//g')
```

Replace with:
```bash
val=$(echo "$line" | sed -E 's/^\s+estimated-tokens:\s*~?//')
# Handle K/M suffixes
if echo "$val" | grep -qi 'k'; then
  val=$(echo "$val" | sed 's/[^0-9.]//g')
  val=$(awk "BEGIN {printf \"%.0f\", $val * 1000}")
elif echo "$val" | grep -qi 'm'; then
  val=$(echo "$val" | sed 's/[^0-9.]//g')
  val=$(awk "BEGIN {printf \"%.0f\", $val * 1000000}")
else
  val=$(echo "$val" | sed 's/[^0-9]//g')
fi
```

- [ ] **Step 2: Re-test parse-queue.sh with the fixture**

```bash
~/.claude/skills/night-shift/scripts/parse-queue.sh --project /tmp/night-shift-test/fake-project/NIGHTSHIFT.md | python3 -m json.tool
```

Expected: `train-ablation` now has `estimated_tokens: 2000000` (not 2). `lint-fix` has `estimated_tokens: 100000`.

---

## Task 8: End-to-End Integration Test

**Files:**
- Create: `/tmp/night-shift-test/e2e-project/NIGHTSHIFT.md`

- [ ] **Step 1: Create a test project with an e2e job**

```bash
mkdir -p /tmp/night-shift-test/e2e-project
cat > /tmp/night-shift-test/e2e-project/NIGHTSHIFT.md << 'E2EEOF'
# Night Shift Queue — e2e-project

## Pending

- [ ] **e2e-hello-world** — Write "hello from night-shift" to /tmp/night-shift-test/output.txt.
  submitted: 2026-06-30
  type: custom
  priority: normal
  estimated-tokens: ~50k
  model-hint: auto
  prompt: |
    Write the text "hello from night-shift" to the file /tmp/night-shift-test/output.txt.
    Create the directory if it doesn't exist.
    Return { success: true, summary: "Done" }.

## Done

## Failed
E2EEOF
```

- [ ] **Step 2: Verify parse**

```bash
~/.claude/skills/night-shift/scripts/parse-queue.sh --project /tmp/night-shift-test/e2e-project/NIGHTSHIFT.md | python3 -m json.tool
```

Expected: 1 pending job, id=`e2e-hello-world`, `estimated_tokens: 50000`, correct prompt text.

- [ ] **Step 3: Simulate a full dispatch cycle**

Run each step manually and verify:
```bash
# 1. Check window
WINDOW=$(~/.claude/skills/night-shift/scripts/check-window.sh --json | python3 -c "import sys,json; print(json.load(sys.stdin)['window'])")
echo "Window: $WINDOW"

# 2. Estimate cost
~/.claude/skills/night-shift/scripts/estimate-cost.sh --tokens 50000 --model pro --window "$WINDOW" --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Cost: {d[\"total_cost_cny\"]} CNY')"

# 3. Config is valid
python3 -c "import json; json.load(open('$HOME/.claude/night-shift/config.json')); print('Config: OK')"
```

Expected: All three pass — valid window, valid cost estimate, valid config.

- [ ] **Step 4: Clean up test fixtures**

```bash
rm -rf /tmp/night-shift-test
# Don't remove the symlink if it was created in ~/.claude/projects/
rm -f ~/.claude/projects/fake-project
```

---

## Task 9: Set Up Initial Cron

- [ ] **Step 1: Set up the daily off-peak cron**

This step requires Claude Code to be running with the ToolSearch-loaded CronCreate tool.

The SKILL.md instructs Claude to run:
```
ToolSearch query: "select:CronCreate,CronDelete,CronList,ScheduleWakeup"
```

Then create the primary cron:
```
CronCreate({
  cron: "5 18 * * *",
  prompt: "Run night-shift dispatch cycle: check window, parse all project queues, dispatch pending jobs within budget. Update NIGHTSHIFT.md status after each job. Follow L2 autonomy rules from ~/.claude/night-shift/config.json.",
  recurring: true,
  durable: true
})
```

- [ ] **Step 2: Verify cron is active**

```
CronList()
```

Expected: Shows the nightly cron job, recurring daily at 18:05.

- [ ] **Step 3: (Optional) Add supplementary crons**

If the user wants lunch-gap or overnight dispatch:
```
CronCreate({ cron: "5 12 * * *", prompt: "(same dispatch prompt)", recurring: true, durable: true })
CronCreate({ cron: "5 0 * * *", prompt: "(same dispatch prompt)", recurring: true, durable: true })
```

---

## Verification Checklist

After all tasks complete, run through this checklist:

- [ ] `check-window.sh` correctly identifies peak vs off-peak for Beijing time
- [ ] `check-window.sh --simulate` produces correct output for both peak and off-peak
- [ ] `estimate-cost.sh` produces correct CNY estimates for all model×window combos
- [ ] `parse-queue.sh` correctly parses NIGHTSHIFT.md with mixed job states
- [ ] `parse-queue.sh --all` discovers projects and aggregates
- [ ] `config.json` is valid JSON and contains all required fields
- [ ] `SKILL.md` has valid YAML frontmatter and is in the skills directory
- [ ] `/night-shift:status` displays correct window and queue state
- [ ] `/night-shift:submit` appends a job to the correct NIGHTSHIFT.md
- [ ] Dispatch workflow: implementer → verifier → status update
- [ ] Peak hold behavior: during peak, large jobs wait for off-peak
- [ ] Retry logic: failed jobs retry up to retry_max, then escalate
- [ ] Budget cap: daily_max_tokens exceeded → hold jobs
- [ ] L2 gate: asks for confirmation before peak Pro dispatch
- [ ] CronCreate fires at 18:05 Beijing daily
