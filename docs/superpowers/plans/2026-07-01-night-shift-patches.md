# night-shift: Adversarial Test Results & Patch Plan

**Status:** 14 adversarial waves completed. ~45 vulnerabilities found.
**Report date:** 2026-07-01
**Goal:** Close all Critical/High gaps before L2 deployment.

---

## Executive Summary

The night-shift skill was pressure-tested by 14 adversarial subagents across 11 domains.
**3 Critical** and **7 High** vulnerabilities require patching before the skill is
publish-ready. All remaining issues are Medium/Low — acceptable for initial L2 deployment.

---

## CRITICAL VULNERABILITIES (Must Fix)

### C1. `state.json` Midnight Reset Missing
**Source:** Adversarial agent (L2/L3 gates)
**What:** `spent_today` is never reset at midnight Beijing time. Budget tracking
        breaks on day 2 — all jobs held forever.
**Fix:** Add `day` field to state.json. Pre-flight checks `last_scan` against current
        date. If date changed, reset `spent_today` before budget check.

### C2. Cron Fires Without Skill Loaded
**Source:** Adversarial agent (cron management)
**What:** The cron prompt is injected into a fresh session. The night-shift skill is
        NOT auto-loaded. The agent has no pricing awareness, routing matrix, or
        non-negotiable rules.
**Fix:** The cron prompt must explicitly tell the agent to load the skill:
        `"You have the night-shift skill at ~/.claude/skills/night-shift/SKILL.md.
         Read it and follow its dispatch protocol precisely."`

### C3. NIGHTSHIFT.md Prompt Capture Bug
**Source:** Adversarial agent (NIGHTSHIFT.md injection)
**What:** Blank lines between prompt text and section headers cause `in_prompt` to
        reset. Prompts are silently dropped for all standard-formatted NIGHTSHIFT.md
        files.
**Fix:** `parse-queue.sh` `in_prompt` flag must not reset on blank lines that are
        still inside an active prompt block. Change the heuristic to check for
        section header pattern (`^## `) rather than blanket non-indented-line reset.

---

## HIGH VULNERABILITIES (Should Fix)

### H1. Config/Pricing File Integrity
**Source:** Adversarial agent (config manipulation)
**What:** No guard against modifying `pricing.json` rates to near-zero or
        `daily_max_tokens` to astronomical values. Config files are "Editable: Yes"
        with no constraints.
**Fix:** Add Non-Negotiable Rule #6: "Do not modify pricing.json rates or config.json
        thresholds. Only add project paths. If pricing changes, ask the user first."
        Add a sanity-check script `validate-config.sh`.

### H2. Model Type→Role Classification Ambiguity
**Source:** Adversarial agent (model routing)
**What:** No formal mapping from job `type` (ml-training, fix, lint, etc.) to
        routing role (Plan/Reason vs Execute/Verify). Agent discretion allows
        any job to be classified as Plan/Reason, routing to Pro during peak.
**Fix:** Add explicit type→role mapping table in SKILL.md:
  - `ml-training` → Plan/Reason
  - `benchmark` → Execute/Verify
  - `fix` → Execute/Verify
  - `refactor` → Plan/Reason
  - `lint` → Execute/Verify
  - `custom` → Ask user or use Execute/Verify

### H3. Dispatch Concurrency
**Source:** Multiple adversarial agents
**What:** No distributed lock, no in-progress state, no atomic check-and-set.
        Two crons or a cron + manual dispatch can dispatch the same job twice.
**Fix:** Add `<!-- dispatching: timestamp -->` annotation to NIGHTSHIFT.md entries
        before dispatch. Append state to prevent re-dispatch. Cleanup on crash
        requires human intervention (acceptable for L2).

### H4. Verifier Runs Unconditionally (Fix Code)
**Source:** Adversarial agent (verifier/state)
**What:** The verifier is SKIPPED when implementer returns `success: false`.
        Maker gates checker.
**Fix:** Change Workflow code to always run verifier. The verifier checks
        *whether the implementer actually failed or lied*.
```javascript
// Instead of: if (!result) return fail
// Run verifier on EVERY dispatch:
phase('Verify')
const verdict = await agent(
  `Task: "${args.prompt}"\n` +
  `Implementer reported: ${result.success ? 'SUCCESS' : 'FAILURE'}\n` +
  `Summary: ${result.summary}\n` +
  `Artifacts: ${(result.artifacts || []).join(', ')}\n\n` +
  `Verify the result. Was the implementer correct?`,
  { model: 'flash', schema: VERDICT_SCHEMA }
)
return { success: verdict?.pass ?? false, summary: result.summary, issues: verdict?.issues }
```

### H5. Crash Recovery / Orphaned Worktrees
**Source:** Adversarial agent (error recovery, workflow dispatch)
**What:** No crash recovery. Worktrees orphaned. Same job re-dispatched silently.
**Fix:** Add `--recover` mode to parse-queue.sh that checks for stale
        `<!-- dispatching -->` annotations older than 1 hour and resets them to pending.
        Add to cron dispatch cycle as step 0.

### H6. No Cron ID Storage
**Source:** Adversarial agent (cron management)
**What:** Cron IDs from CronCreate are never persisted. Config changes orphan old
        crons. No documented CronDelete workflow.
**Fix:** Add `cron_ids: {}` to state.json to map schedule names to CronCreate return
        IDs. Document CronDelete workflow in SKILL.md.

### H7. Field Validation in parse-queue.sh
**Source:** Adversarial agent (NIGHTSHIFT.md injection, UX edge cases)
**What:** Missing fields (type, priority, estimated-tokens) silently omitted from
        JSON. No dedup for duplicate job-ids. No bounds check for token values.
        Overflow from extreme values crashes parser.
**Fix:** `parse-queue.sh` should:
  - Default `type: "custom"`, `priority: "normal"`, `model_hint: "auto"` when missing
  - Warn on duplicate job-ids (log to stderr, keep first)
  - Clamp estimated-tokens to reasonable range (e.g., 0-100M)
  - Handle regex edge cases (leading whitespace, emoji/unicode)

---

## MEDIUM VULNERABILITIES (Document)

| ID | Issue | Fix |
|----|-------|-----|
| M1 | Job-id collision on truncation | Truncate to 36 chars + 4-char hex suffix |
| M2 | API key zeroing (pricing.json rates=0) | Add `night-shift/scripts/validate-config.sh` |
| M3 | "Cost trivially small" rationalization | Add Counter-Table entry |
| M4 | Empty queue cron burn (~50 tokens) | Add "if empty, exit immediately" to cron prompt |
| M5 | Overlapping Symlinked projects | Resolve `realpath` during project discovery; dedup |
| M6 | `--simulate` in production | Add production-mode guard that ignores --simulate |
| M7 | Script staleness | Add note: "ignore previous script results; re-run" |
| M8 | `peak_force_flash` ghost field | Either implement or remove from config.json template |

---

## Patch Sequence

1. **Fix parse-queue.sh** (C3, H7) — prompt capture bug, field defaults, bounds check
2. **Fix SKILL.md Non-Negotiable Rules** (H1, all C-level) — add rules, add Counter-Table entries  
3. **Fix SKILL.md Dispatch Protocol** (H4) — unconditional verifier, concurrency annotation
4. **Fix SKILL.md Cron section** (C2, H6) — self-loading prompt, ID storage
5. **Fix SKILL.md Routing** (H2) — type→role mapping table
6. **Add validate-config.sh** (H1, M2)
7. **Fix SKILL.md Error Recovery** (H5) — --recover mode documentation
8. **Final re-test** — re-run adversarial agents against patched skill

---

## Verification (Post-Patch)

- [ ] Re-run all 14 adversarial scenarios
- [ ] No Critical vulnerabilities remain
- [ ] No High vulnerabilities remain (accepted or fixed)
- [ ] parse-queue.sh handles blank-line prompt format correctly
- [ ] Budget survives midnight boundary
- [ ] Verifier runs unconditionally
- [ ] Type→role mapping prevents route manipulation
- [ ] Cron prompt loads skill correctly
- [ ] Duplicate job-ids handled gracefully
