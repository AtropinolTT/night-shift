#!/usr/bin/env bash
# parse-queue.sh — Parse project NIGHTSHIFT.md files and output aggregated JSON
# Reads pricing.json for context. Outputs validated job queue state.
#
# Usage:
#   parse-queue.sh --project <path>      Parse a single NIGHTSHIFT.md
#   parse-queue.sh --all                 Scan all discovered projects and merge
#   parse-queue.sh --discover            List paths of all found NIGHTSHIFT.md files

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$($SCRIPT_DIR/config-dir.sh)"

MODE="all"
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) TARGET="$2"; MODE="project"; shift 2 ;;
    --all) MODE="all"; shift ;;
    --discover) MODE="discover"; shift ;;
    *) shift ;;
  esac
done

# --- Midnight budget reset ---
# Checks if state.json's day differs from current Beijing date.
# If so, resets spent_today to 0 for the new day.
reset_midnight_budget() {
  local state_file="$CONFIG_DIR/state.json"
  local today
  today=$(TZ='Asia/Shanghai' date +%Y-%m-%d)

  if [[ ! -f "$state_file" ]]; then
    # Create initial state file
    cat > "$state_file" << EOFJSON
{"day":"$today","spent_today":0,"jobs_dispatched_today":0,"last_dispatch":"never","cron_ids":{}}
EOFJSON
    return
  fi

  local state_day
  state_day=$(python3 -c "
try:
    with open('$state_file') as f:
        import json
        d = json.load(f)
    print(d.get('day', ''))
except:
    print('')
" 2>/dev/null || echo "")

  if [[ -n "$state_day" && "$state_day" != "$today" ]]; then
    python3 -c "
import json
with open('$state_file') as f:
    d = json.load(f)
d['day'] = '$today'
d['spent_today'] = 0
d['jobs_dispatched_today'] = 0
with open('$state_file', 'w') as f:
    json.dump(d, f, indent=2)
" 2>/dev/null || true
  fi
}

# --- Parse a single NIGHTSHIFT.md into pending jobs JSON array ---
# Uses quoted heredoc to prevent shell injection into Python.
# Variables are passed via environment, not string interpolation.
parse_file() {
  local file="$1"
  local project
  project=$(basename "$(dirname "$(realpath "$file" 2>/dev/null || echo "$file")")" 2>/dev/null || echo "unknown")

  if [[ ! -f "$file" ]]; then
    echo '[]'
    return
  fi

  # Export for safe Python heredoc access (no shell interpolation)
  export NS_PROJECT="$project"
  export NS_FILE="$file"

  python3 << 'PYEOF'
import sys, json, re, os

jobs = []
current = None
current_section = None
in_prompt = False
prompt_lines = []
seen_ids = set()
project = os.environ["NS_PROJECT"]
filepath = os.environ["NS_FILE"]

with open(filepath) as f:
    for line in f:
        line = line.rstrip()

        # --- Section detection ---
        if line.startswith('## Pending'):
            current_section = 'pending'
            continue
        elif line.startswith('## Done') or line.startswith('## Failed'):
            if in_prompt:
                current['prompt'] = '\n'.join(prompt_lines)
                in_prompt = False
                prompt_lines = []
            current_section = None
            continue
        elif line.startswith('## '):
            if in_prompt:
                current['prompt'] = '\n'.join(prompt_lines)
                in_prompt = False
                prompt_lines = []
            current_section = None
            continue

        if current_section != 'pending':
            continue

        # --- Job header: "- [ ] **job-id** — Description." ---
        m = re.match(r'^- \[ \] \*\*([^*]+)\*\*\s*[—\-]\s*(.*?)(?:\.)?$', line)
        if m:
            if current:
                if in_prompt:
                    current['prompt'] = '\n'.join(prompt_lines)
                jobs.append(current)
            job_id = m.group(1).strip()
            desc = m.group(2).strip()

            if job_id in seen_ids:
                print(f"WARNING: duplicate job-id '{job_id}' in {project}/NIGHTSHIFT.md", file=sys.stderr)
            seen_ids.add(job_id)

            current = {
                'id': job_id,
                'project': project,
                'description': desc,
                'status': 'pending',
                'type': 'custom',
                'priority': 'normal',
                'model_hint': 'auto'
            }
            in_prompt = False
            prompt_lines = []
            continue

        if not current:
            continue

        # --- Metadata fields ---
        m = re.match(r'^\s+submitted:\s*(.+)', line)
        if m:
            current['submitted'] = m.group(1).strip()
            continue
        m = re.match(r'^\s+type:\s*(.+)', line)
        if m:
            current['type'] = m.group(1).strip()
            continue
        m = re.match(r'^\s+priority:\s*(.+)', line)
        if m:
            current['priority'] = m.group(1).strip()
            continue
        m = re.match(r'^\s+estimated-tokens:\s*~?(\d+\.?\d*)\s*([kKmM]?)?', line)
        if m:
            val = float(m.group(1))
            suffix = (m.group(2) or '').lower()
            if suffix == 'k': val *= 1000
            elif suffix == 'm': val *= 1000000
            val = max(0, min(int(val), 100_000_000))
            current['estimated_tokens'] = val
            continue
        m = re.match(r'^\s+model-hint:\s*(.+)', line)
        if m:
            current['model_hint'] = m.group(1).strip()
            continue
        m = re.match(r'^\s+attempts:\s*(\d+)', line)
        if m:
            current['attempts'] = int(m.group(1))
            continue

        # --- Prompt capture ---
        m = re.match(r'^\s+prompt:\s*\|', line)
        if m:
            in_prompt = True
            prompt_lines = []
            continue

        if in_prompt:
            m = re.match(r'^\s{4,}(.*)', line)
            if m:
                prompt_lines.append(m.group(1))
            else:
                # Only end prompt on section header or new job
                if re.match(r'^## ', line) or re.match(r'^- \[ \] \*\*', line):
                    current['prompt'] = '\n'.join(prompt_lines)
                    in_prompt = False
                    prompt_lines = []
                else:
                    # Blank line inside prompt: preserve as empty line
                    if line == '':
                        prompt_lines.append('')

# Flush last job
if current:
    if in_prompt:
        current['prompt'] = '\n'.join(prompt_lines)
    jobs.append(current)

print(json.dumps(jobs, indent=2, ensure_ascii=False))
PYEOF
}

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

# --- Main ---
case "$MODE" in
  project)
    if [[ -z "$TARGET" ]]; then
      echo '{"error":"--project requires a path"}' >&2
      exit 1
    fi
    parse_file "$TARGET"
    ;;
  discover)
    find_queues
    ;;
  all)
    # Step 0: Midnight budget reset
    reset_midnight_budget

    # Step 1: Discover and parse all queues
    QUEUES=($(find_queues))
    echo -n '{"last_scan":"'"$(TZ='Asia/Shanghai' date -Iseconds)"'","projects":{'
    FIRST=true
    for q in "${QUEUES[@]}"; do
      PROJ=$(basename "$(dirname "$(realpath "$q")")")
      if $FIRST; then FIRST=false; else echo -n ','; fi
      echo -n '"'"$PROJ"'":'
      parse_file "$q"
    done
    echo '}}'
    ;;
esac
