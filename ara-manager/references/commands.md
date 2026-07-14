# ARA Manager — Command Reference

Exhaustive per-command reference with edge cases, worked examples, and the exact
YAML / Markdown the command writes. Use this when you need to handle a tricky
case or understand exactly what the command produces.

## Project resolution

Every command (except `init`, `help`) needs a project path. `compile` and `update` resolve
a project path when one exists; if none is found they stage observations in a loose buffer.
Resolution order:

1. `--dir <path>` flag in `$ARGUMENTS` → use that path as `$ARA_DIR`.
2. `./ara/` exists → use it.
3. `./<subdir>/PAPER.md` exists (any depth 1 subdir) → use that subdir.
4. Otherwise → error, print the init hint.

**`@ara` token stripping**: Before resolution, strip any token equal to `@ara` from
`$ARGUMENTS`. This token is user-friendly noise — `update @ara with docs/` is parsed
identically to `update with docs/`.

Once resolved, **all paths in this document are relative to `$ARA_DIR`**.

## `init` — Initialize a new ARA project

### Usage

```
/ara-manager init "My Project Title" --domain NLP --keywords "transformer,attention,ML" --abstract "..."
/ara-manager init "Untitled" --dir /path/to/project
```

### Behavior

- Refuses to overwrite: if `PAPER.md` exists at the target, error and exit.
- Creates the full directory tree (idempotent if run twice; `mkdir -p` is fine).
- Seeds every required file with a minimal but valid stub.

### Seed file templates

**`PAPER.md`**:
```markdown
---
title: "{title}"
authors: ["unknown"]
year: {current year}
venue: "in progress"
doi: "N/A"
ara_version: "1.0"
domain: "{domain or 'unspecified'}"
keywords: [{keywords as YAML list}]
claims_summary: []
abstract: "{abstract or 'TBD'}"
---

# {title}

## Overview
TBD — fill in 1-2 paragraphs once the project scope is clear.

## Layer Index

### Cognitive Layer (`/logic`)
| File | Description |
|------|-------------|
| [problem.md](logic/problem.md) | Observations → gaps → key insight |
| [claims.md](logic/claims.md) | Falsifiable claims |
| [concepts.md](logic/concepts.md) | Formal term definitions |
| [experiments.md](logic/experiments.md) | Declarative experiment plans |
| [related_work.md](logic/related_work.md) | Typed dependency graph |
| [solution/constraints.md](logic/solution/constraints.md) | Boundary conditions |

### Physical Layer (`/src`)
| File | Description |
|------|-------------|
| [environment.md](src/environment.md) | Reproducibility (deps, hardware, seeds) |

### Exploration Graph (`/trace`)
| File | Description |
|------|-------------|
| [exploration_tree.yaml](trace/exploration_tree.yaml) | Research DAG |
| [pm_reasoning_log.yaml](trace/pm_reasoning_log.yaml) | Manager's organizational decisions |
| [sessions/](trace/sessions/) | Per-day session records |

### Evidence (`/evidence`)
| File | Description |
|------|-------------|
| [README.md](evidence/README.md) | Index mapping every evidence file to claims |
```

**`logic/claims.md`**:
```markdown
# Claims

<!-- New claims are crystallized from staging/observations.yaml by /ara-manager crystallize. -->
```

**`logic/problem.md`**, **`logic/concepts.md`**, **`logic/experiments.md`**,
**`logic/related_work.md`**: each `# {Title}` with a one-line comment about its purpose.

**`logic/solution/constraints.md`**: `# Constraints` with a one-line comment.

**`src/environment.md`**: `# Environment` with sections for Software / Hardware / Data / Seeds / Protocols (all empty).

**`trace/exploration_tree.yaml`**:
```yaml
# Research DAG for {title}.
# Nodes: questions (root), decisions, experiments, dead_ends, pivots.
# See references/ara-quick-ref.md for the full schema.

tree: []
```

**`trace/pm_reasoning_log.yaml`**:
```yaml
entries: []
```

**`trace/sessions/session_index.yaml`**:
```yaml
sessions: []
```

**`staging/observations.yaml`**:
```yaml
# Crystallization buffer.
# New observations are staged here. They only move to logic/ on a closure signal
# (affirmation / abandonment / resolution / commitment). See SKILL.md crystallize.

observations: []
```

**`evidence/README.md`**:
```markdown
# Evidence Index

This directory holds the raw proof that backs the artifact's claims. Every
numbered table and figure from the source gets both a markdown transcription
and a PNG screenshot under `tables/` and `figures/`.
```

### After init

Print:
```
[ara-manager] Initialized ARA project at $ARA_DIR.
  Files: N
  Next: /ara-manager add-claim "..." or /ara-manager log decision "..."
```

---

## `status` — Project state dashboard

### Usage

```
/ara-manager status
/ara-manager status --json
```

### Reads

- `PAPER.md` (title, domain)
- `logic/claims.md` (parse all `## C{XX}:` blocks, count by `Status:`)
- `staging/observations.yaml` (count non-promoted entries; count `stale: true` entries)
- `trace/exploration_tree.yaml` (count nodes by `type:`)
- `trace/sessions/session_index.yaml` (last session id and turn_count)
- Latest session record's `open_threads:` (count)

### Output (text mode)

```
ARA Project: Attention Is All You Need
Domain:      Natural Language Processing
Location:    ./ara/

Claims (8 total):
  supported     3   ███
  testing       2   ██
  hypothesis    1   █
  weakened      0
  refuted       1   █
  withdrawn     0
  untested      1   █

Staged observations: 4  (1 stale ≥ 3 days)
Exploration nodes:   12  (3 questions, 4 decisions, 3 experiments, 1 dead-end, 1 pivot)
Open threads:        2  (see latest session record)
Last session:        2026-04-27  (turns: 14)
```

If a section is empty, show `0` (or `(none)` for stages with names).

### Output (JSON mode)

```json
{
  "title": "Attention Is All You Need",
  "domain": "Natural Language Processing",
  "location": "./ara/",
  "claims": {
    "hypothesis": 1, "untested": 1, "testing": 2,
    "supported": 3, "weakened": 0, "refuted": 1, "withdrawn": 0
  },
  "staged": 4,
  "stale": 1,
  "nodes": {
    "question": 3, "decision": 4, "experiment": 3,
    "dead_end": 1, "pivot": 1
  },
  "open_threads": 2,
  "last_session": {"date": "2026-04-27", "turn_count": 14}
}
```

---

## `briefing` — Full project briefing

### Usage

```
/ara-manager briefing
```

### Reads

- Latest `trace/sessions/YYYY-MM-DD_NNN.yaml`:
  - `summary`, `open_threads`, `ai_suggestions_pending`, last `key_context`
- `logic/claims.md` (status counts, plus non-supported claims for context)
- `staging/observations.yaml` (non-stale, non-promoted entries, grouped by `potential_type`)
- `trace/pm_reasoning_log.yaml` (last 10 entries)
- `trace/exploration_tree.yaml` (open question nodes — type=question with no children that resolve them)

### Output sections (in order)

1. **Last session** — date, turn count, summary line.
2. **Open threads** — list each as a bullet.
3. **Pending AI suggestions** — list each.
4. **Key context** — most recent `key_context` excerpt (verbatim, in a blockquote).
5. **Staged observations near closure** — for each non-stale, non-promoted entry:
   ```
   - O{XX} [claim, bound: N03,N05]: "{first 100 chars of content}"
   ```
   Group by `potential_type`.
6. **Stale observations** — entries with `stale: true`:
   ```
   - O{XX} (N days stale) [claim]: "{first 100 chars}"
   ```
7. **Claims status counts** — same as `status`.
8. **Open exploration questions** — list `type: question` nodes with no resolving child:
   ```
   - N01: "Can we build a competitive sequence model without recurrence?"
   - N05: "..."
   ```
9. **Recent PM reasoning** — last 5 entries from `pm_reasoning_log.yaml` (verbatim).

If no session record exists, print the "fresh project" message and the open-questions
list only.

---

## `tree` — Print the exploration DAG

### Usage

```
/ara-manager tree
/ara-manager tree --node N03
/ara-manager tree --depth 2
/ara-manager tree --type dead_end
/ara-manager tree --type decision --node N01
```

### Output

Indented tree with box-drawing characters. Each line:

```
N{XX} [{type}] {title}
    {type-specific field, first 80 chars}
```

- `decision`: `choice: ... [alternatives: N]`
- `experiment`: `result: ...`
- `dead_end`: `failure_mode: ... | lesson: ...`
- `pivot`: `from: X → to: Y | trigger: Z`
- `question`: `description: ...`

Dead-end nodes get a `×` prefix; pivots get a `↪` prefix. Children are indented under
their parent.

### Example

```
N01 [question] Can we build a competitive sequence model without recurrence?
    description: RNNs are sequential bottlenecks. Can self-attention alone handle sequence...
  N02 [experiment] Train Transformer on WMT 2014 EN-DE
      result: 28.4 BLEU on EN-DE, surpassing all previous single models
  N03 [decision] Use sinusoidal positional encodings
      choice: Fixed sinusoidal encodings over learned embeddings [alternatives: 2]
  ↪ N04 [pivot] Switch from learned to fixed positional encodings
      from: learned positional embeddings
      to: fixed sinusoidal encodings
      trigger: Table 3 ablation shows nearly identical performance, fixed is simpler
  × N05 [dead_end] Use sparse attention with top-k=64
      failure_mode: training divergence at step ~5000
      lesson: top-k sparse attention lacks inductive bias for long-range deps; full attention is more stable
```

---

## `log` — Log a journey fact

### Usage

```
/ara-manager log decision "Chose AdamW over SGD" --alternatives "SGD,RMSProp"
/ara-manager log experiment "Trained ResNet-50 on ImageNet, 76.3% top-1"
/ara-manager log dead_end "Tried LayerNorm before attention — diverged at step 1000" --lesson "Pre-norm is essential for stability"
/ara-manager log pivot "Switched from learned to fixed positional encodings"
/ara-manager log question "Can we train without warmup?"
```

### Type-specific schema

For each type, the description is split into the required fields by best-effort
heuristic. If a required field can't be inferred, leave it as an empty string and warn
the user.

**`question`**:
```yaml
- id: N{XX}
  type: question
  title: "<short title>"
  provenance: <p>
  timestamp: "<ts>"
  support_level: explicit
  description: > # the full description
    <description>
  children: []
```

**`decision`**:
```yaml
- id: N{XX}
  type: decision
  title: "<short title>"
  provenance: <p>
  timestamp: "<ts>"
  support_level: explicit
  choice: >           # the chosen option
    <derived from description>
  alternatives:       # list of strings
    - "<from --alternatives or derived>"
  evidence: []        # list of node ids / claim ids from --evidence
  children: []
```

**`experiment`**:
```yaml
- id: N{XX}
  type: experiment
  title: "<short title>"
  provenance: <p>
  timestamp: "<ts>"
  support_level: explicit
  result: >           # the result
    <description>
  evidence: []        # list of evidence file paths or claim ids
  children: []
```

**`dead_end`**:
```yaml
- id: N{XX}
  type: dead_end
  title: "<short title>"
  provenance: <p>
  timestamp: "<ts>"
  support_level: explicit
  hypothesis: >       # what was being tried
    <derived>
  failure_mode: >     # how it failed
    <derived or empty>
  lesson: >           # what was learned
    <from --lesson or derived>
  children: []
```

**`pivot`**:
```yaml
- id: N{XX}
  type: pivot
  title: "<short title>"
  provenance: <p>
  timestamp: "<ts>"
  support_level: explicit
  from: ""            # prior direction
  to: ""              # new direction
  trigger: ""         # what caused the change
  children: []
```

### Heuristics for field derivation

- `title`: strip leading "I", "we", "the", "let me", "let's", then truncate to ≤60 chars.
- `choice` (decision): first sentence or "Chose X" pattern.
- `alternatives` (decision): from `--alternatives` (comma-separated) OR extract "X vs Y" / "X over Y" / "X instead of Y" patterns.
- `result` (experiment): first sentence; preserve any numbers verbatim.
- `hypothesis` (dead_end): "Tried X" pattern; "Tried X — failed because Y" → hypothesis=X, failure_mode=Y.
- `lesson` (dead_end): from `--lesson` if provided; else look for "learned that" / "turns out" / "key takeaway" patterns.
- `from` / `to` (pivot): "switch from X to Y" / "X → Y" patterns; if only one is found, ask.

### Edge cases

- Description is empty → abort, print usage hint.
- `--alternatives` provided to a non-decision type → warn and ignore.
- A `dead_end` log without a `lesson` → warn, set `lesson: ""`, surface in next briefing for user follow-up.

---

## `update` — Scan inputs or project state (lightweight)

### Usage

```
/ara-manager update                                   # print usage
/ara-manager update with docs/handoffs/               # scan docs and stage observations
/ara-manager update claims                            # review claim statuses
/ara-manager update obs                               # review staged observations
/ara-manager update status                            # alias for status
```

### Behavior

Splits into sub-modes based on `args[0]`:

**`with <path>`**: Read files in path, extract knowledge, stage observations.
- Recurse into `.md` and `.yaml` files. Skip binary/PDF (note in output).
- For each extracted fact, stage as observation with appropriate `potential_type`.
- Present each to user for confirmation before staging.
- Output:
```
[ara-manager] update with docs/:
  + O114 (claim) — "Methods audit found 9 discrepancies, 8 fixed"
  + O115 (experiment) — "Ranking HPO R8 running on cloud"
  Skipped (4 PDF files in LNP_reference/)
```

**`claims`**: Read all claims, cross-reference with experiments and staged obs.
- Suggest which claims could advance status. Do NOT advance without confirmation.
```
[ara-manager] update claims:
  C07 (testing) → candidate for supported — falsification criteria met
```

**`obs`**: Scan non-promoted, non-stale observations. Suggest crystallization candidates.
- Group by potential_type. Suggest plausible closure signals.
- Do NOT crystallize without user confirmation.

**`status`**: Alias for the `status` command (see `status` section).

### Edge cases

- Path does not exist → error, show available paths.
- Path contains only skipped files → print "no new observations extracted".
- No non-promoted observations for `update obs` → print "nothing ready for crystallization".

---

## `add-claim` / `add-heuristic` / `add-concept` / `add-constraint`

### Usage

```
/ara-manager add-claim "The model achieves >90% accuracy on dataset X" --tags perf,baseline
/ara-manager add-heuristic "Use cosine LR schedule with 5-epoch warmup" --code src/train.py
/ara-manager add-concept "batch_size" --def "Number of samples per gradient update"
/ara-manager add-constraint "Memory limit: 24GB GPU" --scope "training only"
```

### Behavior

- All four commands stage a new observation in `staging/observations.yaml` with the
  matching `potential_type`. The observation stays staged until `crystallize` is called.
- `add-claim` runs a soft falsifiability check on the content:
  - If the content contains any of "we should", "let's try", "I want to", "we will",
    "going to" → warn, do not block.
  - If the content is a single number, vague noun phrase, or imperative → warn.
  - The warning is informational; staging proceeds.
- `add-concept` and `add-constraint` need the term / title as the first arg. If `--def`
  / `--limit` is missing, ask once; if the user says "skip", stage with `content:` only.

### Schema (all four)

```yaml
- id: O{XX}
  timestamp: "<ts>"
  provenance: <p>     # default: ai-suggested (or user if quoted)
  content: "<content>"
  context: "<derived from $ARGUMENTS or last user turn>"
  potential_type: claim | heuristic | concept | constraint
  bound_to: [<N{XX}>, ...]   # from --bound-to
  promoted: false
  promoted_to: null
  crystallized_via: null
  stale: false
```

### Default provenance

- If the description is in first person / uses "I" / "we" / quotes the user → `user`.
- If the description sounds like the AI generating an inference → `ai-suggested`.
- Never default to `user-revised` (must be an explicit user revision).

---

## `crystallize` — Promote a staged observation

### Usage

```
/ara-manager crystallize O03 --via affirmation
/ara-manager crystallize O07 --via resolution
/ara-manager crystallize O12 --via commitment --provenance user
/ara-manager crystallize O15 --via abandonment
```

### Behavior

1. Look up `O{XX}` in `staging/observations.yaml`. If not found, error.
2. If `--via` is missing, ask: "Which closure signal applies? (affirmation | abandonment | resolution | commitment)".
3. Validate the signal is appropriate:
   - `affirmation` — the user explicitly endorsed the observation. If you can't point
     to a verbatim first-person endorsement in this turn's user input, refuse.
   - `abandonment` — the observation's topic has had no events for the last several turns
     AND `open_threads` does not reference it. (You can use a heuristic: check the
     observation's `bound_to` nodes for any events in the last session records.)
   - `resolution` — an experiment in `bound_to` produced a result and the user commented
     on it. **If the result refutes the observation, crystallize to a `dead_end` node
     in the tree instead.**
   - `commitment` — a downstream artifact (decision node, config, code, or subsequent
     claim) depends on it. Check the latest session record and recent tree nodes.
4. Allocate the next ID in the target layer:
   - `claim` → read `logic/claims.md`, find highest `C{NN}`, use `C{NN+1}`.
   - `heuristic` → read `logic/solution/heuristics.md` (create if missing), find highest
     `H{NN}`, use `H{NN+1}`.
   - `concept` → read `logic/concepts.md` (create if missing). Use the observation's
     `content` as the term; if a section with the same term exists, refuse (or merge).
   - `constraint` → read `logic/solution/constraints.md`. Use the observation's
     `content` as the title.
   - `architecture` → read `logic/solution/architecture.md` (create if missing).
5. Write the typed entry per the schema (see `ara-quick-ref.md`).
6. Update the observation: `promoted: true`, `promoted_to: <layer>:<id>`,
   `crystallized_via: <signal>`. **Do not delete the observation.**
7. If the observation is crystallizing to a claim, also update `PAPER.md`'s
   `claims_summary:` list with a one-line summary (derived from the claim's
   `Statement`).

### Crystallized entry templates

**Claim**:
```markdown
## C{NN}: {title}
- **Statement**: {content}
- **Status**: hypothesis
- **Provenance**: {provenance}
- **Falsification criteria**: pending
- **Proof**: [pending]
- **Dependencies**: []
- **Tags**: {from observation's bound_to or context}
- **Crystallized via**: {signal}
- **From staging**: O{XX}
```

**Heuristic**:
```markdown
## H{NN}: {title}
- **Rationale**: {content}
- **Status**: active
- **Provenance**: {provenance}
- **Sensitivity**: unknown
- **Code ref**: {from --code or [pending]}
- **Crystallized via**: {signal}
- **From staging**: O{XX}
```

**Concept**:
```markdown
## {term}
- **Definition**: {content}
- **Status**: active
- **Provenance**: {provenance}
- **Used in**: []
- **Crystallized via**: {signal}
- **From staging**: O{XX}
```

**Constraint**:
```markdown
## {title}
- **Limit**: {content}
- **Scope**: {from --scope or "unspecified"}
- **Source**: {from observation's context}
- **Crystallized via**: {signal}
- **From staging**: O{XX}
```

### Edge cases

- `potential_type: unknown` → refuse; ask the user to specify the target type first.
- A claim with no falsification criteria → write `pending` and warn.
- Concept term already exists → refuse; suggest either merging or renaming.
- Crystallizing a claim when the user has not provided any falsification criteria →
  warn but proceed (crystallization is rarely blocked; the user can fill in later).

---

## `advance-claim` — Update claim status

### Usage

```
/ara-manager advance-claim C03 testing --note "E05 launched, results pending"
/ara-manager advance-claim C03 supported --note "E05 result 92.3% confirms claim"
/ara-manager advance-claim C07 refuted --note "E12 result 71% — below threshold, claim doesn't hold"
```

### Behavior

1. Read the claim from `logic/claims.md`. If `C{XX}` not found, error.
2. Check the transition is allowed:

   | From → To | Allowed? | Notes |
   |-----------|----------|-------|
   | `hypothesis` → `testing` | yes | normal |
   | `hypothesis` → `supported` | only with both empirical-resolution AND affirmation signals; else suggest `testing` first |
   | `testing` → `supported` | yes | needs empirical resolution |
   | `testing` → `weakened` | yes | needs empirical resolution |
   | `testing` → `refuted` | yes | needs empirical resolution; append `dead_end` |
   | `hypothesis` → `refuted` | yes | terminal |
   | `hypothesis` → `withdrawn` | yes | terminal |
   | `supported` → `weakened` | REFUSE — flag contradiction, ask user to adjudicate |
   | `supported` → `refuted` | REFUSE — needs user directive + append contradiction flag |
   | `refuted` → anything | REFUSE — must go through `revised` first |
   | `withdrawn` → anything | REFUSE — must go through `revised` first |
   | `*` → `revised` | yes | sets `Status: revised`, requires subsequent `revise-claim` call to settle |
   | `*` → `hypothesis` | only from `revised` (after `revise-claim` rewrites Statement) |

3. Update `- **Status**:` field in the claim.
4. Update `- **Last revised**:` to today.
5. If transitioning to `refuted`, append a `dead_end` node to `trace/exploration_tree.yaml`:
   ```yaml
   - id: N{XX}
     type: dead_end
     title: "{claim title} (refuted)"
     provenance: <user from --provenance>
     timestamp: "<ts>"
     support_level: explicit
     hypothesis: "<claim Statement>"
     failure_mode: "<from --note or 'see --note'>"
     lesson: "[pending — user to fill]"
     children: []
   ```
   The dead_end node gets `evidence: [C{XX}]`.
6. Record the change in the latest session's `logic_revisions:` block:
   ```yaml
   - turn: <N>
     entry: C{XX}
     field: Status
     before: "{old status}"
     after: "{new status}"
     signal: empirical-resolution | user-directive
     provenance: <user>
     note: "<--note value>"
   ```
   If no session record exists for today, create one with `turn_count: 1` and
   `turn: 1` for the revision.

### Edge cases

- `--note` missing → ask once; if user skips, write `note: "(no note provided)"` and
  warn in the briefing.
- The session record file is full / write fails → fall back to writing
  `pm_reasoning_log.yaml` with a one-line note about the missed revision.
- Transitioning to `revised` (the transition marker) → the user MUST call
  `revise-claim C{XX}` next; otherwise `revised` is left dangling. Warn.

---

## `revise-claim` — Rewrite claim content

### Usage

```
/ara-manager revise-claim C03 --statement "The model achieves >85% (not 90%) on dataset X" --note "Tightened scope based on E05 result"
/ara-manager revise-claim C07 --rationale "..." --falsification "..." --note "..."
```

### Behavior

1. Read the claim. If `C{XX}` not found, error.
2. For each field the user passed, validate:
   - `--statement`: must remain a falsifiable assertion. If the new text is
     imperative / action-oriented / vague, refuse.
   - `--rationale`: free text.
   - `--falsification`: must be non-trivial (not just "if it doesn't work").
3. Set `Status: revised` (transition marker).
4. Update `- **Last revised**:` to today.
5. Record in session's `logic_revisions:` block with `before` / `after` for each field.
6. After this call, the user must call `advance-claim C{XX} <new-status>` to settle
   the claim to a non-revised status (typically `testing` or `hypothesis`).

### Falsifiability check (heuristic)

The new `Statement` is rejected as un-falsifiable if ALL of the following hold:
- No number, no measurable quantity, no specific behavior is named.
- No scope qualifier ("on dataset X", "under conditions Y", "for inputs with property Z").
- The text is purely qualitative ("works well", "is good", "is robust").

If any of the above is missing, warn but proceed (the user is closer to a falsifiable
claim than they were).

---

## `validate` — Seal Level 1

### Usage

```
/ara-manager validate
/ara-manager validate --stdout    # print to stdout instead of validation_report.md
/ara-manager validate --dir /path/to/ara
```

### Checks (17 total)

**Directory & file presence**:
1. `PAPER.md` exists, YAML frontmatter parses, has `title`, `year`, `claims_summary`.
2. `logic/{problem,claims,concepts,experiments,related_work}.md` exist and are non-empty.
3. `logic/solution/constraints.md` exists and is non-empty.
4. `src/environment.md` exists and is non-empty.
5. `trace/exploration_tree.yaml` exists and parses.
6. `evidence/README.md` exists.
7. `staging/observations.yaml` exists and parses.

**Cross-layer binding**:
8. Every claim's `Proof:` references experiment IDs that exist in `experiments.md`.
9. Every experiment's `Verifies:` references claim IDs that exist in `claims.md`.
10. Tree `evidence:` fields referencing `C{XX}` resolve to claims.
11. Heuristic `Code ref:` paths exist in `src/` (only when both exist).

**Provenance hygiene**:
12. Every claim has a `Provenance:` field with one of the four valid values.
13. Every claim has a `Falsification criteria:` field.

**Exploration tree hygiene**:
14. Tree nodes declare `support_level`.
15. `dead_end` and `pivot` nodes have non-empty `lesson` / `trigger` (warn).

**Self-consistency**:
16. `PAPER.md` `claims_summary` count matches `## C{XX}:` block count.
17. IDs are unique within each file (no two `C{NN}` with the same N).

### Output

```
[validate] Seal Level 1: PASS  (17/17 checks)

or

[validate] Seal Level 1: FAIL  (14/17 checks)
  F08: Claim C03 "Proof: [E99]" — E99 not in logic/experiments.md
  F11: Heuristic H02 "Code ref: src/foo.py" — file not found
  F16: PAPER.md claims_summary lists 5, but logic/claims.md has 4 claim blocks.
```

If `--stdout`, print to stdout; otherwise write to `validation_report.md` at the
artifact root.

### For deeper checks

For figure-vs-markdown consistency, screenshot presence, source-citation verification,
and the full Seal Level 1 spec, first run `compile` on the artifact to regenerate state,
then re-run `validate`.

---

## `review` — Seal Level 2 (delegated)

Always prints:

```
[ara-manager] For Seal Level 2 (semantic epistemic review), invoke:
  /rigor-reviewer $ARA_DIR
```

If the artifact is small (<10 claims, <20 evidence files), the user can ask to do a
quick inline review covering just the six dimension headers without scoring — but the
recommendation is still to use the dedicated skill for a full audit.

---

## `compile` — Deep-read inputs, epistemic extraction, generate artifact (thorough)

### Usage

```
/ara-manager compile docs/                              # 3-pass extraction from docs/
/ara-manager compile docs/handoffs/ docs/plans/         # multi-input
/ara-manager compile docs/ --crystallize                # also auto-crystallize ready observations
/ara-manager compile docs/ --output /path/to/output     # write validation report elsewhere
/ara-manager compile                                    # scan CWD for common input patterns
```

### Behavior

3-pass deep extraction protocol:

**Pass 1 — Inventory**: Read all input files. Extract every distinct factual claim,
design decision, experimental outcome, concept definition, constraint, and heuristic.
For each, capture source file, excerpt, type.

**Pass 2 — Classify + Dedup**: Determine `potential_type` for each fact. Cross-reference
against existing ARA state:
- Semantic match → skip with note
- Refines existing entry → suggest revision (do NOT revise without user confirmation)
- Novel → prepare for staging

**Pass 3 — Stage + optional Crystallize**: Append novel observations to
`staging/observations.yaml`. If `--crystallize`, check each for a clear closure signal
(experiment completed, user affirmed). Auto-crystallize with `resolution` (experiments)
or `commitment` (code/config changes). Then run `validate` (Seal Level 1).

### Output

```
[ara-manager] compile docs/
  Pass 1: 12 facts extracted from 3 files
  Pass 2: 8 novel, 3 duplicates, 1 refinement suggested
  Pass 3: 8 observations staged (4 claims, 2 concepts, 1 constraint, 1 heuristic)
  Validate: Seal Level 1 — PASS (17/17)
```

### Edge cases

- Path contains binary/PDF files → mention in output, suggest manual extraction
- No ARA project exists → still extract and stage loose observations; tell user to `init` first
- `--crystallize` without a project → refuse; crystallization needs an existing ARA project

---

## `organize` — Multi-agent ARA maintenance loop

### Usage

```
/ara-manager organize scout                               # read-only health report
/ara-manager organize extract docs/handoffs/              # scan docs for new observations
/ara-manager organize crystallize                         # propose crystallization candidates
/ara-manager organize audit                               # propose claim status advancements
/ara-manager organize clean                               # stale flags + validate
/ara-manager organize all                                 # full pipeline
/ara-manager organize daily                               # L1 maintenance (scheduled daily 23:30)
/ara-manager organize                                     # print usage (no sub-mode)
/ara-manager organize <unknown>                           # print available sub-modes
```

### Behavior

Splits into sub-modes based on `args[0]` (after extracting `subcommand=organize`).

**`scout`**: Read-only health report. Reads `ara/logic/claims.md`, `ara/staging/observations.yaml`, `ara/trace/exploration_tree.yaml`, `ara/logic/experiments.md`. Writes nothing. Returns structured claim counts, staging stats, tree stats.

**`extract <path>`**: Scan file/directory at `<path>` for research findings not yet in ARA. Reads the target path and existing staging state (for dedup). Appends novel observations to `ara/staging/observations.yaml`. Ignores binary/PDF files.

**`crystallize`**: Analyze non-promoted, non-stale observations in `ara/staging/observations.yaml`. Propose which are ready for crystallization with suggested closure signals. Read-only (proposals presented for user review).

**`audit`**: Analyze claims in `ara/logic/claims.md` for status advancement opportunities. Cross-references with `ara/logic/experiments.md`. Read-only.

**`clean`**: Run structural validation + housekeeping. Set `stale: true` on observations older than 7 days without activity. Detect duplicates. Check structural integrity. Writes stale flags to staging.

**`all`**: Full pipeline: scout → extract (from default paths) → crystallize + audit → review (Opus) → respond (Sonnet) → execute → verify.

**`daily`**: L1 maintenance mode. Runs scout + housekeep + validate. Writes report to `ara/daily/<date>.md`. Does NOT write to any live chat session.

### Edge cases

- **Empty args** (no sub-mode): Print usage listing all sub-modes:
  ```
  [ara-manager] organize: missing sub-mode. Available: scout | extract | crystallize | audit | clean | all | daily
  ```
- **Unrecognized sub-mode**: Print same usage with "unrecognized sub-mode".
- **`@ara` stripping**: `organize @ara all` → `@ara` stripped, same as `organize all`.
- **`extract` with no `<path>`**: Print "extract: missing path. Usage: organize extract <path>".
- **No ARA project**: Error with "No ARA project found" message (standard resolution).

### Implementation

Delegates to Workflow `.claude/workflows/ara-organize.js`. The SKILL.md handles:
1. Parsing `$ARGUMENTS` → extract `subcommand=organize` + sub-mode
2. Validating the sub-mode
3. Printing the invocation message
4. Leaving the actual work to the workflow engine

The workflow engine handles agent dispatch, review loops, file writes, and daily report generation. This command is the user-facing entry point; the workflow is the backend.

---

## Generic rules

1. Read the target file before writing. Find the highest existing ID. Increment.
2. Maintain layer mutability: `logic/` rewrites; `trace/`, `staging/`, `evidence/` only append.
3. Update cross-references after every write (e.g. new claim → update `claims_summary`).
4. Refuse to advance status across forbidden transitions; suggest an alternative.
5. Always print a one-line summary on success.
6. If a command would have no effect (e.g. description missing), print usage and exit.
