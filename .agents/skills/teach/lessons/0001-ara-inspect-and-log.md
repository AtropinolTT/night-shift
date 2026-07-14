# Lesson 1: Inspect & Log — Keeping Your ARA Alive

## Why This Matters

Your ARA project at `./ara/` already captures 7+ claims, 50+ exploration nodes,
and a full experiment log for MARLIN. But research is ongoing — R11 HPO is running,
the physicochemical predictor is evolving, and new findings happen every session.

An ARA project is only as valuable as it is **current**. The two skills here —
**inspecting** (what's the state?) and **logging** (how do I record?) — are the
foundation for keeping your ARA alive.

---

## The Four Layers (Quick Refresher)

| Layer | Mutability | Purpose | Example |
|-------|-----------|---------|---------|
| `logic/` | Mutable (rewritten) | Current best understanding | `claims.md` — C01..C08 |
| `trace/` | Append-only | Journey: decisions, experiments | `exploration_tree.yaml` — N01..N50+ |
| `staging/` | Append-only | Buffer before formalization | `observations.yaml` — O001..O1xx |
| `evidence/` | Append-only | Raw proof | `figures/`, `tables/` |

> **Rule of thumb:** You write to `staging/` and `trace/` frequently.
> `logic/` only changes when a staged observation **crystallizes** into a formal claim.

---

## Command 1: `status` — The Dashboard

Run this first, every session. It tells you what's happening at a glance.

```
! /ara-manager status

ARA Project: MARLIN: Manifold-constrained Attention Residuals for LNP Interpretable Network
Domain:      Computational Biology / Drug Discovery — Molecular Property Prediction
Location:    ./ara/

Claims (N total):
  supported     3   ███
  testing       2   ██
  hypothesis    1   █
  withdrawn     1   █

Staged observations: 12  (2 stale ≥ 3 days)
Exploration nodes:   53  (18 decisions, 12 experiments, 4 dead-ends, 8 pivots, 11 questions)
Open threads:        3   (see latest session record)
Last session:        2026-06-24  (turns: 47)
```

Key info at a glance:
- **Claim statuses** — how many are supported vs testing vs hypothesis
- **Staged observations** — knowledge waiting to be formalized
- **Exploration nodes** — the shape of your research
- **Open threads** — dangling conversations

Add `--json` for machine-readable output.

---

## Command 2: `briefing` — The Full Picture

Where `status` is the dashboard, `briefing` is the sitrep. Run at session start.

```
! /ara-manager briefing

Last session: 2026-06-24, 47 turns — "R11 HPO launched, physicochemical predictor analysis"
Open threads:
  #1 — R11 HPO results pending (expected ~4h)
  #2 — Physicochemical predictor R2 report needs review

Staged observations near closure:
  O114 (claim) — R10 achieves 0.6581 ROC-AUC → signal: resolution (complete)
  O115 (claim) — XAI demo passes 448/468 rows → signal: affirmation (confirmed)

Stale observations (≥3 days):
  O089 (heuristic) — "2-stage screening draft" [5 days] → needs triage

Claims: 3 supported, 2 testing, 1 hypothesis, 1 withdrawn, 0 refuted
```

> **Pre-session ritual:** Open Claude Code → `/ara-manager briefing` → know exactly
> where you are. Costs < 1 second.

---

## Command 3: `tree` — The Exploration History

Every decision, experiment, dead-end, pivot, and question is tracked in a DAG.

```
! /ara-manager tree

N01  [decision] Adopt 7-phase migration plan
N07  [decision] Standardize on PyTorch Lightning
├─ N08  [experiment] Try big-bang rewrite
│  └─ × N09  [dead_end] Big-bang fails — too many entangled deps
N26  [question] Does Z-score normalization improve organ-level ranking?
├─ N27  [experiment] Compare raw vs Z-score normalized targets
│  └─ N28  [decision] Adopt ORGAN_STATS normalization
...
```

Useful flags:
- `--node N12` — subtree only
- `--type experiment` — filter by type
- `--depth 2` — limit depth

---

## The Core Skill: `log` — Recording What Happens

This is THE command you'll use most. Five types:

### `log decision`
A deliberate choice between alternatives.

```
! /ara-manager log decision "Use XGBoost for physicochemical predictor primary model" --provenance user
[ara-manager] Logged N54 (decision) — "Use XGBoost for physicochemical predictor primary model"
```

### `log experiment`
An experiment you ran. Include the outcome, even negative.

```
! /ara-manager log experiment "R11 HPO: LR=0.0005, growth_rate search [0.003,0.025]" --provenance ai-executed
[ara-manager] Logged N55 (experiment) — "R11 HPO launched on gpu1"
```

### `log dead_end`
A path that didn't work. Record *why* and what you learned.

```
! /ara-manager log dead_end "PDI prediction R²≈0 — NaN-imputed zeros drove illusion" --provenance user
[ara-manager] Logged N56 (dead_end) — "PDI prediction fails — artifact mirage"
```

### `log pivot`
A change in direction, with trigger.

```
! /ara-manager log pivot "Switched from RF to XGBoost for feature selection" --provenance user
[ara-manager] Logged N57 (pivot) — "RF → XGBoost for feature selector"
```

### `log question`
An open research question.

```
! /ara-manager log question "Does ensemble uncertainty improve active learning sampling?" --provenance ai-suggested
[ara-manager] Logged N58 (question) — "Ensemble uncertainty for active learning?"
```

### Provenance values (just 4 to remember)

| Value | Meaning |
|-------|---------|
| `user` | You made the call |
| `ai-executed` | Claude ran the experiment |
| `ai-suggested` | Claude proposed it (safe default when unsure) |
| `user-revised` | Claude proposed, you edited |

---

## Bonus: `add-claim` — Staging a New Claim

When you realize something is true but it hasn't been formally claimed yet:

```
! /ara-manager add-claim "Physicochemical predictor EE model achieves R²=0.93 on 5-fold CV" --provenance user --bound-to N30,N45
[ara-manager] Staged O123 (claim) — "Physicochemical predictor EE model achieves R²=0.93 on 5-fold CV"
  Currently staged. Run `/ara-manager crystallize O123 --via` when ready to promote.
```

> The skill checks if your claim is **falsifiable**. If you write "we should try X"
> it'll warn you — that's a decision, not a claim.

---

## The Lifecycle (3-Minute Overview)

```
🔬 Discovery → 📝 log (trace)  or  📋 add-claim (staging) → 💎 crystallize (logic) → 📈 advance-claim
```

1. **Discovery** — you run an experiment, make a decision, realize something
2. **Stage or Trace** — `log` goes to tree; `add-claim` goes to staging
3. **Crystallize** — when confident, promote to `logic/claims.md`
4. **Advance** — as evidence accumulates, move hypothesis → testing → supported

You don't need to crystallize everything today. The staging buffer is for triage.

---

## 🔧 Your Turn: 5-Minute Practice

### Exercise 1 — Check your current state
```
! /ara-manager status
! /ara-manager tree --type question --depth 1
```

### Exercise 2 — Log something real
Think of one thing from your last session. A decision, experiment, or question.
```
! /ara-manager log decision "<what you decided>" --provenance user
```

### Exercise 3 — Stage an observation
A finding you're confident about but haven't claimed yet.
```
! /ara-manager add-claim "<your falsifiable assertion>" --provenance user
```

---

## Quick Reference

| Command | When to use | Writes to |
|---------|-------------|-----------|
| `status` | Every session start | Reads only |
| `briefing` | Deep session start | Reads only |
| `tree` | Navigate history | Reads only |
| `log` | Right after something happens | `trace/exploration_tree.yaml` |
| `add-claim` | Confident finding, not yet formalized | `staging/observations.yaml` |

> **Habit:** Before each session, run `briefing`. After each session,
> run `log experiment "..."`. This two-command habit alone keeps your ARA alive.

---

*Next: Lesson 2 — Crystallize & Advance (promote staged observations into formal claims)*
