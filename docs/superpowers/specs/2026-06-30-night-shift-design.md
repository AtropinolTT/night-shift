# night-shift: Pricing-Aware Agent Orchestration Skill

**Status**: Design (approved, awaiting implementation plan)
**Created**: 2026-06-30
**Target**: Claude Code skill installed at `~/.claude/skills/night-shift/`

## Context

DeepSeek introduced peak/off-peak pricing for V4 models effective mid-July 2026. Peak hours (Beijing time 9:00–12:00, 14:00–18:00) are **2×** off-peak rates. This skill automates job scheduling and model selection to minimize cost while maintaining throughput. It implements loop engineering patterns — the user designs the system that dispatches agents, rather than prompting agents manually.

## Core Capabilities

1. **Job Queue Scheduler** — Submit jobs to project-local queues; night-shift executes them during off-peak windows
2. **Pricing-Aware Model Router** — Automatically routes subagents to Pro vs Flash based on time window, job type, and user config
3. **Loop Orchestrator** — Wraps workflow scripts with pricing awareness so existing agent pipelines benefit from cost optimization

## Architecture

```
User /script or /night-shift:submit
        │
        ▼
┌─────────────────────────────┐
│ NIGHTSHIFT.md (per project) │  ← human-readable queue, git-tracked
│ ~/.claude/night-shift/      │  ← config, state, central queue
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ night-shift SKILL.md        │  ← pricing tables, routing rules, protocols
│ scripts/ (shell)            │  ← deterministic: time-check, cost-est, queue-parse
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ CronCreate + ScheduleWakeup │  ← recurring off-peak wakeup, inter-job pacing
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│ Workflow.js dispatch        │  ← agent() fan-out, worktree isolation, verify subagent
└─────────────────────────────┘
```

## Files to Create

```
~/.claude/skills/night-shift/
  SKILL.md                    ← Main skill (~150 lines)
  references/pricing.md       ← DeepSeek pricing tables
  scripts/
    check-window.sh           ← Returns current Beijing time window
    estimate-cost.sh          ← Token → cost estimate
    parse-queue.sh            ← Reads NIGHTSHIFT.md → structured output
```

## Pricing Tables (reference)

Beijing time (UTC+8). Two peak windows: 9:00–12:00, 14:00–18:00. Off-peak = everything else.

### DeepSeek-V4-Pro

| Billing Item | Off-peak | Peak (2×) |
|---|---|---|
| Input (cache hit) | 0.025 CNY/M | 0.05 CNY/M |
| Input (cache miss) | 3 CNY/M | 6 CNY/M |
| Output | 6 CNY/M | 12 CNY/M |

### DeepSeek-V4-Flash

| Billing Item | Off-peak | Peak (2×) |
|---|---|---|
| Input (cache hit) | 0.02 CNY/M | 0.04 CNY/M |
| Input (cache miss) | 1 CNY/M | 2 CNY/M |
| Output | 2 CNY/M | 4 CNY/M |

## Model Routing Matrix

| Window | model-hint | Agent Role | Selected Model |
|--------|-----------|-------------|----------------|
| Off-peak | auto | Reasoning/Plan | Pro |
| Off-peak | auto | Execute/Verify | Pro |
| Peak | auto | Reasoning/Plan | Pro (costly — gate at L2) |
| Peak | auto | Execute/Verify | Flash |
| Peak | pro (override) | Any | Pro |
| Any | flash (override) | Any | Flash |

L3 peak dispatch threshold is user-configurable in config.json.

## Queue Format: NIGHTSHIFT.md

Each project contains a `NIGHTSHIFT.md`:

```markdown
# Night Shift Queue — <project>

Last dispatch: 2026-06-30 18:10 CST (+8)

## Pending

- [ ] **job-id** — Description.
  submitted: YYYY-MM-DD
  type: ml-training | benchmark | fix | refactor | lint | custom
  priority: high | normal | low
  estimated-tokens: ~2M
  model-hint: auto | pro | flash
  prompt: |
    Multi-line prompt for the agent to execute.
    Can include file paths, commands, etc.

## Done (7-day auto-prune)

- [x] **job-id** — done YYYY-MM-DD | N attempts | ~X tokens

## Failed (needs human)

- [x] **job-id** — failed YYYY-MM-DD | 3 attempts exhausted | [[log]]
```

## Job Lifecycle

```
submitted → pending → dispatch → running → done
                ↓         ↓
              held     failed → retry (≤3) → done | escalated
```

- **held**: Peak window arrived mid-job or user paused
- **failed + retry**: Up to 3 attempts, then escalate
- **escalated**: Written back to NIGHTSHIFT.md with failure log for human review

## Smart Scheduling Rules

| Condition | Action |
|-----------|--------|
| Off-peak + budget available | Dispatch Pro immediately |
| Off-peak + budget exhausted | Hold until tomorrow |
| Peak + job is small (<peak_dispatch_max_tokens) + Flash | Dispatch Flash now |
| Peak + job is large | Hold until off-peak |
| Peak + model-hint = pro | Dispatch Pro (user override) |
| 30 min before peak starts | Pause dispatch, set wakeup for off-peak |

Cross-project parallelism: jobs from different projects can run concurrently (different worktrees, different repos). One job at a time per project.

### Runtime State

`~/.claude/night-shift/state.json` is the machine-facing runtime view — not human-edited. It is rebuilt each cycle from scanning all project `NIGHTSHIFT.md` files. It tracks current dispatch status, token spend today, and active worktrees. On each wakeup, parse-queue.sh regenerates it from source-of-truth queue files.

### Project Discovery

When `projects.discover: true` (default), night-shift finds projects by:
1. Scanning `~/.claude/projects/` for directories with a `NIGHTSHIFT.md`
2. Scanning paths listed in `projects.paths` (optional array in config.json)
3. The blacklist excludes projects by name or path

Any project with a `NIGHTSHIFT.md` is automatically registered. No explicit enrollment needed.

### Deferred Tool Loading

The `CronCreate`, `CronDelete`, `CronList`, and `ScheduleWakeup` tools are deferred — SKILL.md must instruct Claude to load them via `ToolSearch` before first use in a session. This is a Claude Code harness detail, not user-visible.

## Configuration

`~/.claude/night-shift/config.json`:

```json
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
```

## Interactive Commands

| Command | Action |
|---------|--------|
| `/night-shift:submit <project> <prompt>` | Append job to project's NIGHTSHIFT.md |
| `/night-shift:status` | Show all queues, current window, today's spend |
| `/night-shift:run [job-id]` | Force immediate dispatch (bypass window check) |
| `/night-shift:hold <job-id>` | Move job from pending → held |
| `/night-shift:retry <job-id>` | Reset failed job to pending |
| `/night-shift:config` | Show/edit current config |

## L2 → L3 Migration

| Gate | L2 (start) | L3 (target) |
|------|-----------|-------------|
| Peak dispatch | Human approves each | Auto if <peak_dispatch_max_tokens on Flash |
| Budget | 2M/day hard stop | configurable soft cap, auto-throttle |
| Failed jobs | Always escalate | Auto-retry 3×, escalate after exhausted |
| model-hint: pro | Warning + confirm | Honored silently |
| New project queue | Manual review first run | Auto-discover, trust queue |
| Autonomy flag | `"L2"` | `"L3"` |

User upgrades by flipping `autonomy` in config.json and adjusting thresholds.

## Scheduling Strategy

- **Primary cron**: `CronCreate` at 18:05 Beijing daily (right after afternoon peak ends). Covers the long evening/night off-peak window.
- **Supplementary**: Optional `CronCreate` at 12:05 for the lunch gap, at 00:05 for the overnight window.
- **Inter-job pacing**: `ScheduleWakeup` with 5-minute gaps between jobs to avoid token burn.
- **Pre-peak pause**: If 30 minutes remain before peak, pause and wake up after peak ends.

## Verification Plan

| Test | Method |
|------|--------|
| check-window.sh | Manual invocation; verify correct Beijing time window detection |
| parse-queue.sh | Test NIGHTSHIFT.md fixture → verify structured output |
| estimate-cost.sh | Known token counts → verify against pricing table |
| Model routing | Table-driven: every (window × hint × role) combo |
| End-to-end dry run | Submit trivial job → cron fires → status updated to done |
| Peak hold behavior | Simulate peak window → verify job waits |
| Retry logic | Failing job → verify 3 retries → escalation |
| Budget cap | Set cap=1 → verify hold |
