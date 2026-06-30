# night-shift 🌙

**Pricing-aware job scheduler for AI agent loops.** Dispatch expensive reasoning work during cheap off-peak windows. Route subagents to cost-optimal models automatically. Let cron handle the night shift while you sleep.

Built for [DeepSeek V4](https://api-docs.deepseek.com/) peak/off-peak pricing (2× peak multiplier), but the pricing config is externalized — adapt to any model provider with time-based pricing.

```
Peak:     09:00-12:00 + 14:00-18:00 CST → 2× cost
Off-peak: everything else              → base cost
```

## Features

- **⏰ Window-aware dispatch** — checks current pricing window before every job. Never accidentally burns tokens during peak.
- **💰 Cost estimation** — reads live rates from `pricing.json`. Computes Pro vs Flash cost with input/output split and cache hit/miss modeling.
- **📋 Decentralized job queues** — each project has its own `NIGHTSHIFT.md`. Slurm-like, file-based, zero infrastructure.
- **🤖 Model routing matrix** — routes subagents by window × job-type × model-hint. Pro for reasoning, Flash for execution/verification.
- **⏱ Cron scheduling** — fires at configurable off-peak time. Early-exit if peak + >30 min remaining. One job per project at a time.
- **🔐 Maker/checker** — every dispatch has an unconditional verifier. Implementer never gates the checker.
- **📊 Budget controls** — daily token cap, soft/hard mode, per-project concurrency guard.
- **🪜 L2 → L3 autonomy** — L2 (assisted, human-in-the-loop) → L3 (unattended, auto-dispatch with thresholds).

## Quick Start

### Install

```bash
# Clone into Claude Code skills directory
mkdir -p ~/.claude/skills
git clone https://github.com/<your-org>/night-shift ~/.claude/skills/night-shift

# Create config directory
mkdir -p ~/.claude/night-shift

# Copy templates
cp ~/.claude/skills/night-shift/config.example.json ~/.claude/night-shift/config.json
cp ~/.claude/skills/night-shift/pricing.json ~/.claude/night-shift/pricing.json

# (Optional) Verify scripts work
~/.claude/skills/night-shift/scripts/check-window.sh --json
~/.claude/skills/night-shift/scripts/estimate-cost.sh --tokens 100000 --model pro --window off-peak --json
```

> **Note:** If you use a different provider, edit `pricing.json` — see [Configuration](#configuration) below.

### Prerequisites

- **Claude Code** (or any Claude-powered CLI that supports skills)
- **bash** + **python3** (scripts use Python for JSON parsing)
- **CronCreate/CronList/CronDelete** tool availability (for scheduled dispatch)

## Usage

### CLI Commands (via Claude Code)

| Command | What it does |
|---------|-------------|
| `/night-shift:submit <project-path> <description>` | Queue a job for later dispatch |
| `/night-shift:status` | Show window, queues, budget, cron health |
| `/night-shift:run [job-id]` | Force-immediate dispatch (bypasses window) |
| `/night-shift:hold <job-id>` | Move pending → held |
| `/night-shift:retry <job-id>` | Reset failed → pending (resets attempt counter) |
| `/night-shift:config` | Show or update config |

### Queuing a Job

Each project has a `NIGHTSHIFT.md` at its root. Create one with:

```markdown
# NIGHTSHIFT.md — Job Queue

## Pending

- [ ] **train-embedding-v2** — Train embedding model with new loss fn.
  submitted: 2026-07-01
  type: ml-training
  priority: high
  estimated-tokens: ~2M
  model-hint: auto
  prompt: |
    Train embedding model v2 using the new contrastive loss.
    Use `train.py --loss contrastive --epochs 50 --batch-size 256`.
    Log to W&B under project "embedding-v2".

- [ ] **lint-feishu-bridge** — Run linter on feishu-bridge.
  submitted: 2026-07-01
  type: lint
  priority: low
  estimated-tokens: ~50000
  model-hint: auto
  prompt: |
    Run ruff + mypy on feishu-bridge/src/.
```

Then `/night-shift:submit /path/to/project train-embedding-v2` or just let cron pick it up.

### Scheduling Cron

```bash
/night-shift:config --set schedule.off_peak_wakeup=18:05
```

The skill uses `CronCreate` to fire daily at the configured time. Cron prompt explicitly loads the skill so pricing awareness is guaranteed.

## Configuration

### `pricing.json`

Externalized pricing: peak windows, model rates, timezone. **Never hardcoded in the skill.** Update when DeepSeek (or your provider) changes pricing.

```json
{
  "timezone": "Asia/Shanghai",
  "peak_windows": [
    { "start": "09:00", "end": "12:00" },
    { "start": "14:00", "end": "18:00" }
  ],
  "models": {
    "pro": {
      "name": "DeepSeek-V4-Pro",
      "off_peak": {
        "input_cache_hit": 0.025,
        "input_cache_miss": 3,
        "output": 6
      },
      "peak": { "input_cache_hit": 0.05, "input_cache_miss": 6, "output": 12 }
    },
    "flash": {
      "name": "DeepSeek-V4-Flash",
      "off_peak": {
        "input_cache_hit": 0.02,
        "input_cache_miss": 1,
        "output": 2
      },
      "peak": { "input_cache_hit": 0.04, "input_cache_miss": 2, "output": 4 }
    }
  }
}
```

### `config.json`

Runtime configuration — autonomy level, budget, dispatch thresholds.

```json
{
  "autonomy": "L2",
  "budget": {
    "daily_max_tokens": 5000000,
    "soft_cap": false
  },
  "thresholds": {
    "peak_dispatch_max_tokens": 200000,
    "retry_max": 3,
    "escalate_after_failures": 3
  },
  "schedule": {
    "off_peak_wakeup": "18:05",
    "inter_job_pause_minutes": 5
  }
}
```

## Model Routing Matrix

| Window   | model-hint | Role            | Model |
|----------|-----------|-----------------|-------|
| Off-peak | auto      | Any             | Pro   |
| Off-peak | pro       | Any             | Pro   |
| Off-peak | flash     | Any             | Flash |
| Peak     | auto      | Plan/Reason     | Pro   |
| Peak     | auto      | Execute/Verify  | Flash |
| Peak     | pro       | Any             | Pro   |
| Peak     | flash     | Any             | Flash |

### Job Type → Role Mapping (used under `auto`)

| Job Type       | Role            | Peak Model |
|---------------|-----------------|------------|
| `ml-training` | Plan/Reason     | Pro        |
| `benchmark`   | Execute/Verify  | Flash      |
| `fix`         | Execute/Verify  | Flash      |
| `refactor`    | Plan/Reason     | Pro        |
| `lint`        | Execute/Verify  | Flash      |
| `custom`      | Execute/Verify  | Flash      |

## Autonomy Levels

### L2 (Assisted — Default)

| Situation | Behavior |
|-----------|----------|
| Peak + Pro dispatch | Show cost, ask user to confirm — wait indefinitely |
| Peak + Flash, <200k tokens | Auto-dispatch |
| Budget exhausted | Hold, notify user |
| Failed job | Escalate to human |
| New project queue | Ask user before first dispatch |

### L3 (Unattended)

| Situation | Behavior |
|-----------|----------|
| Peak + Pro, <threshold | Auto-dispatch |
| Peak + Pro, >threshold | Hold |
| Peak + Flash | Always auto |
| Budget exhausted, soft_cap | Throttle, warn |
| Budget exhausted, hard | Hold |
| Failed job | Auto-retry up to max, then escalate |
| New project | Auto-discover, trust |

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Cron fires  │────▶│  Cron prompt     │────▶│  check-window   │
│  18:05 CST   │     │  loads skill     │     │  --json         │
└──────────────┘     └──────────────────┘     └────────┬────────┘
                                                        │
                                              ┌─────────▼────────┐
                                              │  Peak or         │
                                              │  off-peak?       │
                                              └────┬────┬────────┘
                                           peak     │    │ off-peak
                                      <30min left   │    │
                                           ┌────────▼┐  │
                                           │Wait for  │  │
                                           │off-peak  │  │
                                           └──────────┘  │
                                                         ▼
                                              ┌──────────────────┐
                                              │  parse-queue     │
                                              │  --all           │
                                              └────────┬─────────┘
                                                       │
                                              ┌─────────▼─────────┐
                                              │  Sort by priority │
                                              │  + submission     │
                                              └─────────┬─────────┘
                                                       │
                                              ┌─────────▼─────────┐
                                              │  Per job:         │
                                              │  pre-flight →     │
                                              │  concurrency →    │
                                              │  route →          │
                                              │  dispatch →       │
                                              │  verify →         │
                                              │  update queue     │
                                              └───────────────────┘
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/check-window.sh [--json] [--simulate peak\|off-peak]` | Current pricing window + time remaining |
| `scripts/estimate-cost.sh --tokens N --model pro\|flash --window peak\|off-peak [--input-ratio 0.5] [--json]` | Token → CNY estimate |
| `scripts/parse-queue.sh --project <path>` | Parse one NIGHTSHIFT.md |
| `scripts/parse-queue.sh --all` | Aggregate all project queues |
| `scripts/parse-queue.sh --discover` | Find all NIGHTSHIFT.md files |

## Project Queue Format (`NIGHTSHIFT.md`)

```markdown
## Pending

- [ ] **<kebab-id>** — <summary>.
  submitted: YYYY-MM-DD
  type: ml-training | benchmark | fix | refactor | lint | custom
  priority: high | normal | low
  estimated-tokens: ~<N>
  model-hint: auto | pro | flash
  prompt: |
    <multi-line instructions for the implementer agent>
```

Defaults: `type=custom`, `priority=normal`, `model-hint=auto`. Token range: [0, 100M].

## Skill Design Principles

Built using [loop engineering](https://github.com/cobusgreyling/loop-engineering) patterns:

- **Maker/checker** — implementer (Pro) + unconditional verifier (Flash). Never grade your own homework.
- **One job per project** — concurrency guard prevents double-dispatch when cron and manual overlap.
- **Scripts before reasoning** — run tools for time math and cost arithmetic. Manual time math is the #1 source of misrouted jobs.
- **Rationalization counter-table** — every known excuse pre-bunked with reality. 16 entries, tested adversarially.
- **Adversarially tested** — 8 rounds of parallel haiku subagents trying to break each rule. Zero exploits remaining.

## File Layout

```
~/.claude/skills/night-shift/
├── SKILL.md              # Main skill definition
├── scripts/
│   ├── check-window.sh   # Window detector
│   ├── estimate-cost.sh  # Cost estimator
│   └── parse-queue.sh    # Queue parser
└── references/           # (future)

~/.claude/night-shift/
├── pricing.json          # Pricing config (user-editable)
├── config.json           # Runtime config (user-editable)
└── state.json            # Runtime state (auto-managed)
```

## Adapting to Other Providers

night-shift is **not DeepSeek-specific**. To adapt:

1. Edit `pricing.json` — change `models`, `peak_windows`, `timezone`
2. (Optional) Update model routing names in `SKILL.md` if your provider uses different model tiers

The pricing is **never hardcoded** in the skill logic. Every cost decision reads from `pricing.json` at runtime.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [Loop Engineering](https://github.com/cobusgreyling/loop-engineering) — patterns for agentic software development loops
- [DeepSeek](https://deepseek.com/) — V4 Pro and Flash models with transparent pricing
- Adversarial testing framework — parallel subagent pressure-testing methodology from [superpowers](https://github.com/claude-plugins-official/superpowers)
