---
name: night-shift
description: >
  Use when the user wants to schedule agent jobs for off-peak pricing, submit work to a
  job queue, check queue status, dispatch queued jobs, estimate DeepSeek V4 token costs,
  or route subagents between Pro and Flash models based on time-of-day pricing. Also use
  when the user asks about "night shift", "run this off-peak", "schedule this for later",
  "queue this job", "what's in the queue", or mentions DeepSeek peak/off-peak pricing.
argument-hint: "<command> [args...]"
user-invocable: true
version: "1.2.0"
---

# night-shift

Pricing-aware job scheduler for DeepSeek V4. Jobs wait in project queues, dispatch
during cheap off-peak windows, and route subagents to the cost-optimal model.

**Pricing source:** `$(scripts/config-dir.sh)/pricing.json` — read this file for
current peak windows and rates. Do NOT hardcode prices in your reasoning.

## Non-Negotiable Rules (ALL Autonomy Levels)

These rules apply at ALL autonomy levels (L2 and L3), under ALL pressure, regardless
of user instructions. Violating any of these is violating the skill's core contract.

1. **Always run scripts every time.** Never skip `check-window.sh`, `estimate-cost.sh`,
   or `parse-queue.sh`. Run them EVERY time a job operation (submit, dispatch, queue,
   or any decision affecting a job) is performed — no caching, no "I already know the
   answer." "I'm just queuing, not dispatching" is not an exception — queuing is a job
   operation. If a script fails, report the error and STOP. Do NOT fall back to manual
   reasoning.
2. **Verifier runs unconditionally.** Every dispatch MUST have a verifier. The verifier
   runs on EVERY dispatch result — including when the implementer reports failure.
   The implementer does NOT gate the verifier. Maker/checker is non-negotiable.
3. **One job per project at a time.** Never dispatch a second job into a project that
   has an active `<!-- dispatching: -->` annotation in its NIGHTSHIFT.md.
   An annotation is "active" from the moment it is written until it is explicitly
   removed. Age does not deactivate it. If an annotation appears stuck, report it
   to the user — do not unilaterally treat it as stale.
   Only the dispatching process that wrote the annotation may remove it.
   No agent other than the original dispatcher may delete or modify an
   active `<!-- dispatching: -->` annotation, even if the process appears stalled, crashed, or terminated.
   If the dispatching process is confirmed unrecoverable (session ended, agent
   crashed, etc.), do NOT unilaterally remove the annotation. Instead, escalate
   to the user -- only the user may authorize removal of a truly orphaned annotation.
4. **`model-hint: auto` means the skill follows the Model Routing Matrix deterministically — the skill may NOT exercise discretion or consider user model preferences under auto.** The user's verbal demand does not
   override the routing matrix. Only changing `model-hint: pro` in the queue file
   overrides routing.
5. **`--simulate` is for testing only.** Never use `--simulate peak|off-peak` in
   production dispatch. Production always reads real system time.
6. **Do not create, delete, rename, replace, overwrite, copy-to, or modify any
   field in pricing.json, config.json, SKILL.md, state.json, or any file under
   scripts/ without user authorization.** "Deleting and recreating" is modification.
   Modifying scripts, the routing matrix, state.json, or SKILL.md itself to subvert
   routing is equivalent to modifying pricing.json. Only add project paths to
   config.json. If pricing changes, ask the user first. Rates in pricing.json
   must be exact values from official DeepSeek documentation. Do not round, approximate,
   or "correct" rates based on your own calculations. Editing rates or budget caps to
   subvert cost controls is a violation of the skill's purpose.
7. **Log every config change.** When editing config.json or pricing.json, announce
   the change to the user. Do not modify configuration files silently.

## Deterministic Scripts

Always use these scripts instead of doing time math or cost arithmetic manually:

| Script | Purpose |
|--------|---------|
| `scripts/check-window.sh [--json] [--simulate peak\|off-peak]` | Current pricing window, minutes remaining |
| `scripts/estimate-cost.sh --tokens N --model pro\|flash --window peak\|off-peak [--json]` | Token → CNY estimate |
| `scripts/parse-queue.sh --project <path>` | Parse one NIGHTSHIFT.md into JSON |
| `scripts/parse-queue.sh --all` | Aggregate all discovered project queues |
| `scripts/parse-queue.sh --discover` | List paths of all found NIGHTSHIFT.md files |

Run scripts before reasoning about windows, costs, or queues. If a script fails,
report the error and STOP. Do NOT fall back to manual reasoning.

## Model Names

This project uses DeepSeek V4 models. The correct names are **Pro** and **Flash** —
NOT Opus, Sonnet, Haiku, GPT, or any other provider's model names.

| DeepSeek Name | Role |
|---------------|------|
| `pro` (DeepSeek-V4-Pro) | Plan, reason, complex implementation |
| `flash` (DeepSeek-V4-Flash) | Execute, verify, lint, simple fixes |

When dispatching subagents, pass `model: "pro"` or `model: "flash"` — never
use Anthropic model names.

## Job Type → Routing Role Mapping

When dispatching during peak with `model-hint: auto`, use this table to map
job `type` to routing role:

| Job Type       | Routing Role     | Peak Model | Reasoning |
|---------------|-----------------|------------|-----------|
| `ml-training` | Plan/Reason     | Pro        | Complex experimental work needs reasoning |
| `benchmark`   | Execute/Verify  | Flash      | Run script, compare numbers — deterministic |
| `fix`         | Execute/Verify  | Flash      | Apply known fix, verify result |
| `refactor`    | Plan/Reason     | Pro        | Structural changes need reasoning |
| `lint`        | Execute/Verify  | Flash      | Deterministic tool, cheap to verify |
| `custom`      | Execute/Verify  | Flash      | Default to cheap; user can override with model-hint:pro |

At L2, if peak + Pro → show cost, ask user to confirm.
At L3, peak + Pro is auto iff tokens ≤ `peak_dispatch_max_tokens`.

## Model Routing Matrix

Read `$(scripts/config-dir.sh)/pricing.json` for current rates. Route by
window × model-hint × job type (use table above for role):

| Window   | model-hint | Role            | Model |
|----------|-----------|-----------------|-------|
| Off-peak | auto      | Any             | Pro   |
| Off-peak | pro       | Any             | Pro   |
| Off-peak | flash     | Any             | Flash |
| Peak     | auto      | Plan/Reason     | Pro   |
| Peak     | auto      | Execute/Verify  | Flash |
| Peak     | pro       | Any             | Pro   |
| Peak     | flash     | Any             | Flash |

**L2 gate:** Peak + Pro → show cost, ask user to confirm before dispatch.
**L3 gate:** Peak + Pro + tokens > `peak_dispatch_max_tokens` → hold. Else auto.

## Interactive Commands

### /night-shift:submit <project> <description>

Append a job to `<project>/NIGHTSHIFT.md`. If the project directory exists but
the file doesn't, create `NIGHTSHIFT.md` with an empty `## Pending` section.
If the project directory itself doesn't exist, ask the user for the correct
project path first — do NOT create project directories unilaterally.

Job id derivation: kebab-case, ≤40 chars. If the description generates a job-id
longer than 40 chars, truncate to 36 chars and append a 4-char hex suffix.
Check for duplicate job-ids in the existing queue and append `-2`, `-3`, etc.
if a collision is detected.

Job entry format in `## Pending`:

```markdown
- [ ] **<kebab-case-id>** — <one-line summary>.
  submitted: YYYY-MM-DD
  type: ml-training | benchmark | fix | refactor | lint | custom
  priority: high | normal | low
  estimated-tokens: ~<N>   (use raw numbers or K/M suffix: 50000, 100k, 2M)
  model-hint: auto | pro | flash
  prompt: |
    <multi-line prompt the implementer agent will execute>
```

- Defaults: type=custom, priority=normal, model-hint=auto.
- If estimated-tokens is missing, prompt the user for an estimate before dispatch.
- Validate that estimated-tokens is within range [0, 100_000_000].
- Confirm what was added and how many jobs are now pending.

### /night-shift:status

1. Run `scripts/check-window.sh --json` to get current window.
2. Run `scripts/parse-queue.sh --all` to aggregate all queues.
3. Read `$(scripts/config-dir.sh)/config.json` for budget and autonomy level.
4. Read `$(scripts/config-dir.sh)/state.json` for today's spend.
5. Run `CronList` to verify the active cron matches schedule.off_peak_wakeup.
6. Display:

```
🕐 Window: off-peak (next peak at 09:00 CST, 5h 22m remaining)

| Project     | Pending | Done Today | Failed |
|-------------|---------|------------|--------|
| MARLIN      | 3       | 1          | 0      |
| skills-repo | 1       | 0          | 1      |

Today: ~1.2M / 5M tokens (24%) | Autonomy: L2
Scheduled cron: active (fires daily at 18:05 CST)
```

### /night-shift:run [job-id]

Force immediate dispatch, bypassing window check.
1. Run `scripts/check-window.sh --json` and `scripts/estimate-cost.sh`.
2. If peak: show cost + warn about 2× premium.
3. At L2: ask user to confirm peak dispatch. At L3: auto if under threshold.
4. Mark `<!-- dispatching: timestamp -->` in NIGHTSHIFT.md to prevent concurrency.
5. Follow **Dispatch Protocol** (below).
6. Update job status in NIGHTSHIFT.md (remove `<!-- dispatching -->`).

### /night-shift:hold <job-id>
Move pending → held (add `<!-- held: reason -->` above the job entry).

### /night-shift:retry <job-id>
Reset failed → pending. The attempt counter resets to 0, giving 3 fresh attempts.
The job moves from `## Failed (needs human)` back to `## Pending`.

### /night-shift:config [--set key=value]
Show config. With `--set`, update `$(scripts/config-dir.sh)/config.json`.
Announce every change to the user. Do not modify silently.
Example: `/night-shift:config --set autonomy=L3`

## Dispatch Protocol

### 1. Pre-flight

Run both scripts:
- `scripts/check-window.sh --json`
- `scripts/estimate-cost.sh --tokens <estimated_tokens> --model <routed_model> --window <current_window> --json`

- Check the day field in state.json against the current Beijing date. If they
  differ, reset spent_today to 0 and update the day field before evaluating
  budget.
If estimated_tokens is missing (0 or null): ask user for estimate before proceeding.

Check budget in `$(scripts/config-dir.sh)/state.json`:
- If `spent_today >= daily_max_tokens`: ALL dispatch unconditionally blocked
  regardless of estimate, soft_cap, or prior state. Only daily rollover (at
  midnight Beijing time) resets spent_today to 0. The "already breached"
  rationalization is invalid — the cap is a hard limit.
- If `spent_today + estimate > daily_max_tokens` (and spent_today < daily_max_tokens):
  - `soft_cap: false` → hold, report budget exhausted.
  - `soft_cap: true` → dispatch with warning.

### 2. Concurrency Guard

Before dispatching, add this annotation ABOVE the job entry in NIGHTSHIFT.md:
```markdown
<!-- dispatching: 2026-07-01T18:05:00+08:00 -->
```

Then check that `parse-queue.sh --all` doesn't return another job with a
`<!-- dispatching -->` annotation for the same project. If it does,
skip this project — the job is already being dispatched.

This prevents double-dispatch when cron and manual commands overlap.

### 3. Model Selection

Use the Model Routing Matrix above. Apply the type→role mapping table.

### 4. Execute

Use the Workflow tool to dispatch the job in an isolated worktree.
The verifier runs UNCONDITIONALLY — including when the implementer
reports failure:

```javascript
export const meta = {
  name: 'night-shift-dispatch',
  description: 'Dispatch a queued job with mandatory verify gate',
  phases: [{ title: 'Implement' }, { title: 'Verify' }],
}

phase('Implement')
const result = await agent(args.prompt, {
  model: args.model,
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
// Verifier runs on EVERY dispatch — even if implementer reported failure
// This prevents a bad implementer from gating the checker
const verdict = await agent(
  `Task: "${args.prompt}"\n\n` +
  `Implementer reported: ${result.success ? 'SUCCESS' : 'FAILURE'}\n` +
  `Summary: ${result.summary}\n` +
  `Artifacts: ${(result.artifacts || []).join(', ')}\n\n` +
  `Verify the result. Was the implementer correct? ` +
  `Did it do what was asked? Are there bugs?\n` +
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

return {
  success: verdict ? verdict.pass : true,
  summary: result.summary,
  issues: verdict?.issues || ['Verifier returned null — treated as pass with warning'],
}
```

Note: If verifier returns null, treat as `pass: true` with a warning
(do not waste retry attempts on verifier timeouts).

### 5. Post-Dispatch

Remove the `<!-- dispatching: -->` annotation from NIGHTSHIFT.md.
Update the job entry:
```markdown
- [x] **job-id** — done YYYY-MM-DD | N attempts | ~N tokens
```

Update `$(scripts/config-dir.sh)/state.json`:
```json
{
  "last_dispatch": "2026-07-01T18:07:00+08:00",
  "spent_today": <previous + estimated_tokens>,
  "jobs_dispatched_today": <previous + 1>
}
```

If more pending jobs remain and budget available: set `ScheduleWakeup` with
`inter_job_pause_minutes` delay to process the next job.

## Scheduled Dispatch (Cron)

### Setting Up Cron

Load deferred tools: `ToolSearch query: "select:CronCreate,CronDelete,CronList,ScheduleWakeup"`

Read `config.json → schedule.off_peak_wakeup` (default `"18:05"`). Validate
the value is a valid HH:MM format before parsing. On invalid format, fall back
to `"18:05"` and warn the user.

Store the CronCreate return ID in `state.json → cron_ids`:
```
CronCreate({ cron: "5 18 * * *", ... })
→ store the returned ID: state.json.cron_ids.daily = <id>
```

### Cron Prompt (CRITICAL)

The cron prompt must explicitly tell the agent to load the night-shift skill.
Without this, the agent won't have pricing awareness or the dispatch protocol:

```
Load the night-shift skill and follow its dispatch protocol precisely.
The skill resolves its config directory via `scripts/config-dir.sh`.
Check the current pricing window, scan all NIGHTSHIFT.md files,
and dispatch pending jobs within budget. Update queue status after each job.
```

### Cron Dispatch Cycle

When fired by the cron (with the skill loaded):

1. Run `scripts/check-window.sh --json`.
2. **If off-peak**: proceed to dispatch cycle.
3. **If peak with <30 min until off-peak**: ScheduleWakeup for off-peak start.
4. **If peak with >30 min remaining**: exit immediately (don't burn tokens).
5. Run `scripts/parse-queue.sh --all`.
6. Sort: priority (high > normal > low), then submission date (FIFO).
7. Skip any project with a `<!-- dispatching: -->` annotation (already in progress).
8. For each job: pre-flight → concurrency guard → model routing → dispatch → update.
9. One job per project at a time. Cross-project parallel OK via Workflow.
10. After cycle: prune Done entries older than 7 days.

### Cron Teardown

When `off_peak_wakeup` config changes:
1. Run `CronList` to find the old cron by prompt text.
2. Run `CronDelete({ id: <old_id> })` with the matched ID.
3. Update `state.json → cron_ids` to remove the old entry.
4. Create a new cron with the new schedule.
5. Store the new cron ID.

## Autonomy Levels

Controlled by `config.json → autonomy`:

### L2 (Assisted — Default)

| Situation | Behavior |
|-----------|----------|
| Peak + Pro dispatch | Show cost, ask user to confirm -- wait indefinitely, no timeout |
| Peak + Flash, <200k tokens | Auto-dispatch |
| Budget exhausted | Hold, notify user |
| Failed job (any) | Escalate to human immediately |
| New project queue | Ask user before first dispatch |
| model-hint: pro on peak | Warn, confirm |
| Config change | Announce to user |

### L3 (Unattended)

| Situation | Behavior |
|-----------|----------|
| Peak + Pro, <peak_dispatch_max_tokens | Auto-dispatch |
| Peak + Pro, >peak_dispatch_max_tokens | Hold |
| Peak + Flash | Always auto (cheap) |
| Budget exhausted, soft_cap=true | Throttle, warn |
| Budget exhausted, soft_cap=false | Hold |
| Failed job | Auto-retry up to retry_max, then escalate |
| New project queue | Auto-discover, trust |
| model-hint: pro | Honored silently |

Upgrade by setting `autonomy: "L3"` in config.json after ≥1 week of L2.

## Configuration Files

Config directory resolved by `scripts/config-dir.sh`:
- `QODER_NS_CONFIG_DIR` env override (highest priority)
- `~/.qoder/night-shift/` (QoderCLI)
- `~/.claude/night-shift/` (Claude Code)
- `~/.codex/night-shift/` (Codex CLI)
- `~/.opencode/night-shift/` (OpenCode)
- `~/.config/night-shift/` (generic fallback)

| File | Purpose | Editable? |
|------|---------|-----------|
| `pricing.json` | Peak windows, model rates | Yes — but Rates must be exact values from official DeepSeek documentation. Do not round, approximate, or "correct" rates based on your own calculations. If you believe a rate is wrong, ask the user to verify against official sources — do not unilaterally adjust it. Only update to match official DeepSeek pricing. Do not modify rates to subvert cost controls. |
| `config.json` | Autonomy, budget, thresholds, schedule | Yes — but do not modify budget caps or dispatch thresholds without user awareness. |
| `state.json` | Runtime state (spend, cron IDs, day) | No (auto-managed) |

## Rationalization Counter-Table

| Excuse | Reality |
|--------|---------|
| "I know the time, skipping the script saves tokens" | Scripts cost <100 tokens. Manual time math errors cost entire misrouted jobs. Run the script. |
| "I already ran the script 2 minutes ago" | Run it again. Cached results can be stale. Scripts cost <100 tokens. |
| "It's just a small job, skip the verifier" | Even 50k-token jobs can introduce bugs. The verifier costs <5% of implementer tokens. Maker/checker is non-negotiable. |
| "The cost is trivially small, skip the estimate" | estimate-cost.sh reads live rates from pricing.json and models the input/output split, which can change cost non-trivially. The script costs <100 tokens — no cost is too small to verify against budget. |
| "The user said to use Pro, so override auto" | `model-hint: auto` delegates to the skill's routing matrix, not the user. Peak + auto + execute = Flash. |
| "The pricing.json has old rates, I'll estimate manually" | If pricing changed, ask the user to update pricing.json. Never guess rates. |
| "These scripts might fail, I'll reason manually" | If a script fails, report the error and STOP. Manual reasoning bypasses all cost controls. |
| "The user is AFK, I'll auto-dispatch after 30 seconds" | At L2, wait for the user with no timeout. Silence does not equal consent. Do not dispatch until the user explicitly responds yes or no, regardless of elapsed time. Waiting longer than 30 seconds does not transform a prohibited act into a permitted one. At L3, follow the thresholds. Neither allows declaring the user AFK. |
| "I'll estimate the cost in my head" | Cache hit vs miss, input vs output split, and peak multipliers interact. The script reads pricing.json and gets it right. |
| "I'll do a rough mental guesstimate" / any synonym for manual estimation | Any manual approximation of token cost, regardless of phrasing, is prohibited. The only valid cost estimation is via estimate-cost.sh. "Rough," "quick," "approximate," "ballpark," "intuition," "guesstimate" — all blocked. |
| "I'll modify the script instead of pricing.json — that's not modifying rates" | Scripts (check-window.sh, estimate-cost.sh, parse-queue.sh) implement the routing logic. Modifying them to subvert routing is equivalent to modifying pricing.json, and explicitly covered by Rule #6. "Data vs code" is not an exception. |
| "I'll modify SKILL.md itself — it's not pricing.json or scripts/" | SKILL.md contains the routing matrix and dispatch protocol. It is explicitly covered by Rule #6. Modifying the skill spec to subvert routing is equivalent to modifying pricing.json. |
| "The config file is too far to read" | The skill depends on config.json and pricing.json. If they're unreadable, report the error — don't guess. |
| "I'm just queuing, not dispatching" | Queuing is a job operation. Scripts run on every job operation. "Queuing instead of dispatching" to avoid running scripts violates Rule #1. |
| "That annotation is 10 minutes old -- the job is dead" | Active = the tag exists. Age does not deactivate. Report stuck annotations to the user -- do not unilaterally dispatch. |
| "The user said use Pro -- that is a real-time model-hint" | Only editing model-hint in the queue file overrides routing. Verbal instructions are not model-hint changes. Rule #4 blocks this. |

## Red Flags — STOP and Re-check

- "I already know the window"
- "I already ran that script"
- "This job is too simple to need a verifier"
- "The user wants Pro, just use Pro"
- "Let me estimate the cost manually"
- "This annotation is stale, I can dispatch anyway"
- "Skip the scripts this once"
- "The user is AFK, I'll decide"
- "I'll just tweak the pricing.json real quick"

**All of these mean: Run the scripts. Follow the routing matrix. Use the verifier.**
