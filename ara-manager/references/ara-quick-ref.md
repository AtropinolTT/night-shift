# ARA Structure Quick Reference

Compact reference for the four-layer ARA structure. Use this when you need to write
into a specific file and want to confirm the field schema, the mutability regime, or
the cross-layer binding rules.

## The four layers

| Layer | Path | Mutability | What it holds |
|-------|------|------------|---------------|
| Cognitive | `logic/` | **Mutable** — overwritten in place as current best understanding | What & Why: problem, claims, concepts, experiments, related work, solution files |
| Physical | `src/` | Mutable | How: environment, configs, code, data, prompts (whatever the work concretely has) |
| Exploration | `trace/` | **Append-only** | Journey: exploration DAG, PM reasoning log, session records |
| Evidence | `evidence/` | **Append-only** | Raw proof: tables (md + png), figures (md + png), proofs |
| Staging | `staging/` | **Append-only** | Crystallization buffer for observations awaiting closure |

> Rule of thumb: `logic/` rewrites in place; everything else only appends. Staging
> observations may set forward-reference pointers (`promoted: true`,
> `promoted_to: ...`) but their bodies stay immutable.

## File-by-file schema

### `PAPER.md`

```yaml
---
title: "..."
authors: [...]      # may be ["unknown"] in early stages
year: 2026
venue: "..."
doi: "arXiv:..."    # or "N/A" if no DOI yet
ara_version: "1.0"
domain: "..."
keywords: [...]
claims_summary:
  - "one-line claim 1"
  - "one-line claim 2"
abstract: "..."
---

# {Title}

## Overview
1-2 paragraph summary.

## Layer Index
### Cognitive Layer (/logic)
| File | Description |
|------|-------------|
| [problem.md](logic/problem.md) | Observations → gaps → key insight |
| [claims.md](logic/claims.md) | N falsifiable claims (C01–C{NN}) |
| ... |

(Repeat table for /src, /trace, /evidence.)
```

### `logic/problem.md`

```markdown
# Problem

## Observations
- O1: <observation with numbers>
- O2: ...

## Gaps
- G1: <what's missing>
- G2: ...

## Key Insight
<the non-obvious move that closes the gaps>

## Assumptions
- A1: <assumption that the work depends on>
- ...
```

### `logic/claims.md`

```markdown
# Claims

## C{XX}: {title}
- **Statement**: <falsifiable assertion, current best wording>
- **Status**: hypothesis | untested | testing | supported | weakened | refuted | withdrawn
- **Provenance**: user | ai-suggested | user-revised
- **Falsification criteria**: <what would disprove this — concrete, scoped>
- **Proof**: [E{XX}, E{YY}, ...]   # experiment IDs from experiments.md
- **Dependencies**: [C{YY}, ...]   # other claim IDs this depends on
- **Tags**: comma-separated
- **Last revised**: YYYY-MM-DD (turn-id)   # absent until first revision
```

Allowed status transitions:

```
hypothesis ──► testing ──► supported
     │            │            ▲
     │            └──► weakened┘
     ├────────────────► refuted    (terminal, empirical)
     ├────────────────► withdrawn  (terminal, non-empirical)
     └─ any ─────────► revised    (transition marker; settle to testing/hypothesis)
```

### `logic/concepts.md`

```markdown
# Concepts

## {term}
- **Definition**: <formal or precise informal definition>
- **Status**: active | deprecated
- **Provenance**: user | ai-suggested | user-revised
- **Used in**: [C{XX}, E{XX}, ...]
- **Last revised**: YYYY-MM-DD
```

### `logic/experiments.md`

```markdown
# Experiments

## E{XX}: {title}
- **Verifies**: [C{XX}, C{YY}, ...]   # claim IDs this tests
- **Setup**: <model / dataset / hardware / seeds — concrete>
- **Procedure**: <step-by-step — concrete, reproducible>
- **Metrics**: <what we measure>
- **Expected outcome**: <directional only — no exact numbers; those go in evidence/>
- **Baselines**: <what we compare to>
- **Dependencies**: [E{YY}, ...]
- **Status**: planned | running | done | inconclusive
```

### `logic/solution/constraints.md`

```markdown
# Constraints

## {constraint title}
- **Limit**: <boundary condition>
- **Scope**: <when / where this applies>
- **Source**: paper §X / repo path / conversation
```

### `logic/solution/heuristics.md`

```markdown
# Heuristics

## H{XX}: {title}
- **Rationale**: <why this works>
- **Status**: active | weakened | retired
- **Provenance**: user | ai-suggested | user-revised
- **Sensitivity**: low | medium | high | unknown
- **Code ref**: [<file paths>, or "pending"]
- **Last revised**: YYYY-MM-DD
```

### `logic/related_work.md`

```markdown
# Related Work

## RW{XX}: {reference key (e.g. vaswani2017attention)}
- **Relation**: imports | extends | bounds | baseline | refutes
- **Delta**: <the specific technical delta vs this work>
- **Source**: <citation>
```

### `src/environment.md`

```markdown
# Environment

## Software
- python: 3.11
- pytorch: 2.1.0
- ...

## Hardware
- GPU: A100 80GB
- ...

## Data
- dataset: <name> @ <version / commit>
- splits: train=..., val=..., test=...

## Seeds
- python: 42
- numpy: 42
- torch: 42
- ...

## Protocols
- train command: <verbatim>
- eval command: <verbatim>
```

### `trace/exploration_tree.yaml`

```yaml
tree:
  - id: N01
    type: question | decision | experiment | dead_end | pivot
    title: "<short>"
    provenance: user | ai-suggested | ai-executed | user-revised
    timestamp: "YYYY-MM-DDTHH:MM"
    support_level: explicit | inferred
    # type-specific fields:
    description: >     # question
    choice: >          # decision
    alternatives: []   # decision
    evidence: []       # decision, experiment
    result: >          # experiment
    hypothesis: >      # dead_end
    failure_mode: >    # dead_end
    lesson: >          # dead_end
    from: ""           # pivot
    to: ""             # pivot
    trigger: ""        # pivot
    children:
      - { ... }        # nested DAG
```

### `staging/observations.yaml`

```yaml
observations:
  - id: O{XX}
    timestamp: "YYYY-MM-DDTHH:MM"
    provenance: user | ai-suggested | ai-executed | user-revised
    content: "<raw observation, factually distilled>"
    context: "<what was happening when this arose>"
    potential_type: claim | heuristic | concept | constraint | architecture | unknown
    bound_to: [N{XX}, ...]   # exploration nodes this depends on
    promoted: false
    promoted_to: null         # e.g. "logic/claims.md:C07" once crystallized
    crystallized_via: null    # which closure signal fired
    stale: false              # true after 3+ session-days with no event
```

### `trace/sessions/YYYY-MM-DD_NNN.yaml`

```yaml
session:
  id: "YYYY-MM-DD_NNN"
  date: "YYYY-MM-DD"
  started: "YYYY-MM-DDTHH:MM"
  last_turn: "YYYY-MM-DDTHH:MM"
  turn_count: 0
  summary: "<rolling one-line>"

events_logged:
  - turn: 1
    type: decision | experiment | dead_end | pivot | observation
    id: "{N/O}{XX}"
    routing: direct | staged | crystallized
    provenance: ...
    summary: "<telegraphic what>"

ai_actions:
  - turn: 1
    action: "<what AI did>"
    provenance: ai-executed
    files_changed: ["<paths>"]

claims_touched:
  - id: C{XX}
    action: created | crystallized | advanced | weakened | confirmed | refuted | withdrawn | revised | split | merged
    turn: 1

logic_revisions:                  # full before/after for every logic edit
  - turn: 1
    entry: C{XX}
    field: Statement | Status | Rationale | ...
    before: "<prior value, verbatim>"
    after: "<new value, verbatim>"
    signal: empirical-resolution | verbal-declaration | dependency-change | artifact-commitment | terminology-drift | user-directive
    provenance: user | ai-suggested | user-revised
    note: "<optional one-line why>"

key_context:
  - turn: 1
    excerpt: "<quote or paraphrase of the decisive exchange>"

open_threads:
  - "<what needs follow-up>"

ai_suggestions_pending:
  - "<unconfirmed AI suggestion still awaiting closure>"
```

### `trace/sessions/session_index.yaml`

```yaml
sessions:
  - id: "YYYY-MM-DD_NNN"
    date: "YYYY-MM-DD"
    summary: "<main outcome>"
    turn_count: N
    events_count: N
    claims_touched: [C{XX}, ...]
    open_threads: N
```

### `evidence/`

```
evidence/
  README.md                     # index mapping every file to claims
  tables/
    table1.md                    # transcription
    table1.png                   # screenshot
    ...
  figures/
    figure1.md                   # transcription / description
    figure1.png                  # screenshot
    ...
  proofs/
    derivation1.md               # as warranted
```

Each `tableN.md` / `figureN.md` should declare:

```markdown
# {Caption}

**Source**: <paper §X, repo path, ...>
**Type**: quantitative_plot | diagram | qualitative_sample | mixed
**Extraction method**: exact_from_labels | digitized_estimate | visual_description
**Reading confidence**: high | medium | low

## Content
<raw content or structured description>
```

## ID conventions

| Type | Prefix | Example | Scope |
|------|--------|---------|-------|
| Exploration node | N | N01 | Global (across all turns and sessions) |
| Claim | C | C01 | Global; assigned at crystallization, not at staging |
| Heuristic | H | H01 | Global; assigned at crystallization |
| Concept | (term) | `## batch_size` | Per-file section; no numeric id |
| Constraint | (title) | `## memory limit` | Per-file section; no numeric id |
| Experiment plan | E | E01 | Global |
| Observation | O | O01 | Global; assigned at staging |
| Session | date_seq | 2026-04-27_001 | Unique per calendar day |
| Evidence | tableN / figureN | table3 | Per-source-numbered |
| Related work | RW | RW01 | Global |

## Closure signals (for crystallize)

A staged observation crystallizes into a typed entry ONLY when one of these signals
fires. Default to non-promotion.

| Signal | Use when |
|--------|----------|
| `affirmation` | User explicitly endorsed the observation this turn in first person ("yes", "confirmed", "ship it"). **Upgrades provenance: `ai-suggested` → `user-revised` (or `user` if reproduced verbatim).** |
| `abandonment` | The observation's topic has had no events for the last several turns AND `open_threads` does not reference it. |
| `resolution` | An experiment in `bound_to` produced a result and the user commented on it. If the result refutes the observation, crystallize to a `dead_end` node, NOT to a claim. |
| `commitment` | A downstream artifact depends on it (decision cites it, config fixed, code merged, or subsequent claim cites it). |

## Cross-layer binding rules

| Binding | Source | Target |
|---------|--------|--------|
| Claim → Proof | `claims.md` `Proof:` | experiment IDs in `experiments.md` |
| Experiment → Verifies | `experiments.md` `Verifies:` | claim IDs in `claims.md` |
| Heuristic → Code | `heuristics.md` `Code ref:` | real file paths in `src/` |
| Decision → Evidence | tree `evidence:` | claim IDs and/or node IDs |
| Dead end → Lesson | tree `lesson:` | non-empty string |
| Observation → Bound | `observations.yaml` `bound_to:` | exploration node IDs |

Stale observations: `stale: true` after 3+ session-days with no event AND not referenced
in `open_threads`. Surfaced at briefing for user triage — never auto-discarded.
