---
name: ara-manager
description: |
  Project management interface for Agent-Native Research Artifacts (ARA). A unified,
  command-based interface to initialize, query, scan, compile, validate, and review
  ARA research projects. Use this skill whenever the user wants to manage a research
  project following the ARA standard — creating a new ARA artifact, checking project
  status, scanning external docs to stage observations (`update with <path>`),
  deep-reading inputs for epistemic extraction (`compile <path>`), logging research
  events (decisions, experiments, dead-ends, pivots, questions), adding claims/
  heuristics/concepts/constraints, crystallizing staged observations, advancing
  claim status, running structural validation (Seal Level 1), running epistemic
  review (Seal Level 2), or improving the architecture of the `src/` layer.

  TRIGGERS: manage ara project, ara status, add claim, log decision, log experiment,
  log dead-end, log pivot, add heuristic, add concept, add constraint, crystallize
  observation, advance claim, validate ara, ara seal level 1, review ara, ara seal
  level 2, ara project briefing, ara init, ara compile, ara tree, ara status,
  update ara with, scan docs for ara, update @ara, update claims, update obs,
  improve architecture, refactor src, deepen module, find seam, ara improve arch,
  ARA 项目管理, 科研项目, ARA 状态, 添加主张, 记录决策, 记录实验, 记录死胡同,
  验证 ARA, 评审 ARA
argument-hint: "<command> [args...]"
allowed-tools: Read, Write, Edit, Bash(mkdir *,ls *,cat *,grep *,find *,date *), Glob, Grep
user-invocable: true
metadata:
  author: ara-commons
  version: "2.0.1"
  category: research-tooling
  tags: [ara, project-management, research, artifact, provenance, knowledge-management, scan, compile]
---

# ARA Project Manager

You are the **ARA Project Manager** — a command-based interface for managing a research
project that follows the [Agent-Native Research Artifact (ARA) standard](https://github.com/Orchestra-Research/Agent-Native-Research-Artifact).

An ARA project is a directory (`./ara/` by default) containing four interlocking layers:

```
ara/
  PAPER.md                          # Root manifest + layer index
  logic/                            # What & Why (mutable — current best understanding)
    problem.md  claims.md  concepts.md  experiments.md  related_work.md
    solution/   (constraints.md + method files as warranted)
  src/                              # How (concrete artifacts)
    environment.md  configs/  execution/  data/  ...
  trace/                            # Journey (append-only)
    exploration_tree.yaml           # Research DAG
    pm_reasoning_log.yaml
    sessions/
  evidence/                         # Raw proof (append-only)
    README.md  tables/  figures/  proofs/
  staging/                          # Crystallization buffer (append-only)
    observations.yaml
```

`logic/` is **mutable** (rewritten in place, current-state snapshot); `trace/`, `staging/`,
and `evidence/` are **append-only**.

---

## Command Parsing

Parse `$ARGUMENTS` to extract a subcommand and its arguments. Split on whitespace;
the first token is the subcommand. **After splitting, strip any token equal to `@ara`
from both the subcommand token and args** — it is noise meaning "operate on the ARA
project" and should not affect dispatch.

Special subcommands with sub-modes (`update`, `compile`) parse their own second-level
tokens from the remaining args.

```
$ARGUMENTS = "<subcommand> [args...]"
```

Examples:
- `init "My Project Title"` → `subcommand=init`, `args=["My Project Title"]`
- `log decision "Chose X over Y"` → `subcommand=log`, `args=[decision, "Chose X over Y"]`
- `add-claim "The model achieves >90% on dataset X"` → `subcommand=add-claim`, `args=[...]`
- `crystallize O03 --via affirmation` → `subcommand=crystallize`, `args=[O03, --via, affirmation]`
- `update with docs/` → `subcommand=update`, `args=[with, docs/]` — see `update` section for sub-mode dispatch
- `update @ara with docs/` → `@ara` stripped, same as `update with docs/`
- `compile docs/ --output ./ara` → `subcommand=compile`, `args=[docs/, --output, ./ara]`
- (no args) → default to `status` if an ARA project exists, else `help`

**Fallback rule**: If the subcommand is not recognized, print a one-line error listing
available commands instead of silently defaulting to `status`. Exception: if `$ARGUMENTS`
is empty or whitespace-only (after stripping `@ara`), fall back to `status` (for bare
`/ara-manager` invocations).

### Project location

Default: `./ara/`. The first subcommand that needs the project should resolve the path by
checking (in order):

1. `--dir <path>` flag in `$ARGUMENTS`
2. `./ara/` (current working directory)
3. Any subdirectory of `.` that contains `PAPER.md` at its root

If no ARA project is found and the command is not `init` or `help`, print an error and exit:

```
[ara-manager] No ARA project found at ./ara/ (or via --dir).
Run `/ara-manager init "Project Title"` to create one, or pass --dir <path>.
```

### Date / time

Use the current system date for `timestamp` and `date` fields. `date` is `YYYY-MM-DD`,
`timestamp` is `YYYY-MM-DDTHH:MM` (24-hour local time, omit seconds).

---

## Command Reference

Each command below lists: purpose, arguments, what it reads, what it writes, and
a worked example. For deeper per-command details, see `references/commands.md`.

| Command | Purpose |
|---------|---------|
| `init` | Create a new ARA project at the resolved directory |
| `status` | Show project state — claim statuses, staged observations, open threads |
| `briefing` | Full briefing: where we left off, open threads, stale observations |
| `tree` | Print the exploration DAG |
| `help` | Show command reference |
| `log` | Log a journey fact (decision / experiment / dead_end / pivot / question) |
| `add-claim` | Add a new claim to `staging/observations.yaml` (potential_type: claim) |
| `add-heuristic` | Add a heuristic observation |
| `add-concept` | Add a concept observation |
| `add-constraint` | Add a constraint observation |
| `crystallize` | Promote a staged observation into `logic/` on a closure signal |
| `advance-claim` | Update a claim's `Status` field in `logic/claims.md` |
| `revise-claim` | Rewrite a claim's `Statement` / `Rationale` and record the diff |
| `validate` | Run Seal Level 1 (structural) checks on the artifact |
| `review` | Delegate to the `rigor-reviewer` skill (Seal Level 2 — epistemic) |
| `compile` | Deep-read inputs, run epistemic extraction, stage + crystallize observations (thorough) |
| `update` | Lightweight scan of inputs or project state — stage observations, review claims/obs |
| `improve-arch` | Analyze `src/` for deepening opportunities (delegates to the `improve-codebase-architecture` skill) |
| `organize` | Multi-agent ARA maintenance loop — scout, extract, crystallize, audit, clean, daily. Orchestrates specialized Haiku agents with Opus review and Sonnet response. |

---

## `init` — Initialize a new ARA project

**Args**: `[title] [--domain <text>] [--keywords k1,k2,...] [--abstract <text>] [--dir <path>]`

**Reads**: nothing (creates fresh).

**Writes** (creates the directory tree + seed files):

```bash
mkdir -p $ARA_DIR/{logic/solution,src,trace/sessions,evidence/{tables,figures},staging}
```

Seed files (all minimal but valid):

1. `$ARA_DIR/PAPER.md` — frontmatter (`title`, `domain`, `keywords`, `claims_summary: []`,
   `abstract`) + Layer Index.
2. `$ARA_DIR/logic/problem.md` — `# Problem` placeholder.
3. `$ARA_DIR/logic/claims.md` — `# Claims` placeholder.
4. `$ARA_DIR/logic/concepts.md` — `# Concepts` placeholder.
5. `$ARA_DIR/logic/experiments.md` — `# Experiments` placeholder.
6. `$ARA_DIR/logic/related_work.md` — `# Related Work` placeholder.
7. `$ARA_DIR/logic/solution/constraints.md` — `# Constraints` placeholder.
8. `$ARA_DIR/src/environment.md` — `# Environment` placeholder (data / software / hardware / seeds).
9. `$ARA_DIR/trace/exploration_tree.yaml` — `tree: []`
10. `$ARA_DIR/trace/pm_reasoning_log.yaml` — `entries: []`
11. `$ARA_DIR/trace/sessions/session_index.yaml` — `sessions: []`
12. `$ARA_DIR/staging/observations.yaml` — `observations: []`
13. `$ARA_DIR/evidence/README.md` — `# Evidence Index`

Refuse to overwrite: if `$ARA_DIR/PAPER.md` already exists, print a warning and exit without
touching anything:

```
[ara-manager] ARA project already exists at $ARA_DIR. 
Use `/ara-manager status` to inspect, or remove the directory first.
```

---

## `status` — Show project state

**Args**: `[--json]` (machine-readable output).

**Reads**: `PAPER.md`, `logic/claims.md`, `staging/observations.yaml`,
`trace/exploration_tree.yaml`, `trace/sessions/session_index.yaml`,
`trace/pm_reasoning_log.yaml`.

**Writes**: nothing.

Print a compact dashboard:

```
ARA Project: <title from PAPER.md>
Domain:      <domain>
Location:    <ara dir>

Claims (N total):
  supported     3   ███
  testing       5   █████
  hypothesis    7   ███████
  weakened      1   █
  refuted       1   █
  withdrawn     0
  untested      2   ██

Staged observations: 4  (1 stale ≥ 3 days)
Exploration nodes:   N  (D decisions, E experiments, X dead-ends, P pivots, Q questions)
Open threads:        M  (see latest session record)
Last session:        YYYY-MM-DD  (turns: T)
```

If `--json`, emit the same data as a JSON object with keys: `title`, `domain`, `claims`
(map of status → count), `staged` (count), `stale` (count), `nodes` (by type),
`open_threads` (count), `last_session` (date + turn_count).

---

## `briefing` — Full briefing

**Args**: none.

**Reads**: latest session record (`trace/sessions/YYYY-MM-DD_NNN.yaml`),
`logic/claims.md`, `staging/observations.yaml` (non-stale, non-promoted),
`pm_reasoning_log.yaml` (last 10 entries), `exploration_tree.yaml` (open questions).

**Writes**: nothing.

Print, in order:

1. **Last session**: date, turn count, rolling one-line summary.
2. **Open threads** (from the latest session's `open_threads:` list).
3. **Pending AI suggestions** (`ai_suggestions_pending:`).
4. **Key context** (the most recent `key_context` excerpt).
5. **Staged observations near closure**: non-stale, non-promoted entries grouped by
   `potential_type`. For each, show: id, `content` (one line), `bound_to` (node ids).
6. **Stale observations**: id, age in days, `content` (one line) — flagged for triage.
7. **Claims status counts** (same as `status`).
8. **Open exploration questions** (tree nodes with `type: question` and no children that
   resolve them).
9. **Recent PM reasoning** (last 5 lines of `pm_reasoning_log.yaml`).

If there is no session record yet, print:

```
[briefing] No sessions recorded yet. This appears to be a fresh ARA project.
Use `/ara-manager log ...` to start recording research events.
```

---

## `tree` — Print the exploration DAG

**Args**: `[--node <N{XX}>]` (show subtree rooted at node), `--depth N` (max depth,
default unlimited), `--type <type>` (filter by node type).

**Reads**: `trace/exploration_tree.yaml`.

**Writes**: nothing.

Render the DAG as an indented tree using box-drawing characters. Each node line shows
`id [type] title` plus the most informative type-specific field:

- `question` → `description` (first 80 chars)
- `decision` → `choice` (first 80 chars) + `[alternatives: N]`
- `experiment` → `result` (first 80 chars)
- `dead_end` → `failure_mode: ... | lesson: ...` (each first 60 chars)
- `pivot` → `from: X → to: Y | trigger: Z`

Mark dead-end nodes with `×` prefix and pivot nodes with `↪` prefix. If `--node N{XX}`
is given, show only that node's subtree. If `--type <t>` is given, filter the visible
nodes to that type (children of filtered nodes still render).

---

## `update` — Scan inputs or project state (lightweight)

**Args**: No sub-mode → print usage. Sub-modes:

| Sub-mode | What it does |
|----------|-------------|
| `with <path>` | Scan files/directories, extract knowledge, stage as observations |
| `claims` | Review claim statuses, suggest which can advance |
| `obs` | Review staged observations, suggest which can crystallize |
| `status` | Alias for the `status` command |

Dispatch on `args[0]` after extracting `subcommand=update`.

**Reads**: depends on sub-mode.

**Writes**: appends to `staging/observations.yaml` for `with <path>`; reads-only for `claims` and `obs`.

### `update with <path>` — Scan external inputs

Read each file/directory in `<path>`, extract knowledge, and stage as observations:

- **Handoffs** (`docs/handoffs/`): extract decisions made, experiments run, claims modified → stage as `claim` or `experiment` observations
- **Plans** (`docs/plans/`): extract design decisions, architecture constraints → stage as `decision` or `constraint` observations
- **Progress reports** (`docs/*-progress.md`): extract experiment outcomes → stage as `experiment` observations
- **Any other file**: extract key facts and stage with appropriate `potential_type`

For each extracted fact, use `add-claim` / `add-heuristic` / `add-concept` / `add-constraint` semantics (append to `staging/observations.yaml`). Ask the user to confirm each observation before staging — don't batch-stage without review.

If path is a directory, recursively find `.md` and `.yaml` files. Skip binary and PDF files (note them in the output as skipped).

Output summary:
```
[ara-manager] update with docs/:
  + O114 (claim) — "Methods-code audit found 9 discrepancies, 8 fixed"
  + O115 (experiment) — "Ranking HPO R8 running on cloud"
  Skipped (4 PDF files in LNP_reference/) — use `compile` for deep extraction
```

### `update claims` — Review claim statuses

Read all claims, cross-reference with experiments and staged observations, and suggest
which claims could advance status. Example:

```
[ara-manager] update claims:
  C02 (supported) → no change needed
  C07 (testing) → candidate for supported — E09 passed, falsification criteria met
  C11 (testing) → candidate for supported — 54 tests pass, GPU validated
```

Do NOT advance status without user confirmation.

### `update obs` — Review staged observations

Scan non-promoted, non-stale observations. Group by `potential_type`. Suggest
candidates for crystallization with plausible closure signals:

```
[ara-manager] update obs:
  Ready for crystallization:
    O76 (claim) — marXAI passes 131/131 → signal: resolution (experiment complete)
    O47 (constraint) — Phase 2 gaps → signal: resolution (all implemented)
  
  Needs discussion:
    O113 (claim) — CLS warmup_epochs discrepancy → pending HPO results
```

Do NOT crystallize without user confirmation.

---

## `log` — Log a journey fact (direct to trace)

**Args**: `<type> <description> [--provenance <p>] [--evidence <id,id,...>]`
Type ∈ `decision | experiment | dead_end | pivot | question`.

**Reads**: `trace/exploration_tree.yaml` (to find the next `N{XX}` id).

**Writes**: appends a node to `trace/exploration_tree.yaml`.

Routing is **direct** (journey facts are not staged). Read the current tree, find the
highest existing `N{XX}` id, allocate the next one, and append:

**No-project fallback**: If no ARA project exists, treat it as a fresh project.
Allocate `N01` as the first trace-tree id. Print the confirmation as usual.
The absence of a project directory does not block logging journey facts.

```yaml
  - id: N{XX}
    type: <type>
    title: "<short title derived from description>"
    provenance: <provenance>
    timestamp: "<YYYY-MM-DDTHH:MM>"
    # type-specific fields per the research-manager schema:
    description: > # for question
      <description>
    choice: >      # for decision
      <description>
    alternatives: []   # decision — may be empty
    evidence: []       # decision, experiment — list of node ids / claim ids
    result: >          # for experiment
      <description>
    hypothesis: >      # for dead_end
      <description>
    failure_mode: >    # for dead_end
      <description>
    lesson: >          # for dead_end
      <description>
    from: ""           # pivot
    to: ""             # pivot
    trigger: ""        # pivot
    children:
```

**Defaults** (paper defines exactly four provenance values: `user | ai-suggested |
ai-executed | user-revised`):
- `provenance`: pick exactly one of the four by the ARA P2 rule:
  - `user` — the description is in first person / quotes the user.
  - `ai-suggested` — the agent proposed it but did not act; the user has not yet
    confirmed. **This is the safe default when uncertain.**
  - `ai-executed` — the agent performed the action (ran an experiment, executed a
    query, generated the result). Use this for `experiment` and `pivot` nodes where
    the agent did the work.
  - `user-revised` — the agent proposed something, the user edited it, the result
    is a hybrid. Never guess this without an explicit revision this turn.
- `title`: ≤ 60 chars, derived from the description (strip leading "I", "we", "the").
- `description` / `choice` / `result` / `hypothesis` / `failure_mode` / `lesson` / `from`
  / `to` / `trigger`: derive from the description by best-effort heuristic. If multiple
  fields apply (e.g. for a dead_end the user only stated a hypothesis), leave the others
  as empty strings and ask the user to fill them on a later turn.
- `evidence`: empty list unless `--evidence` is passed.

Print: `[ara-manager] Logged N{XX} (decision) — "Chose AdamW over SGD"`. The PM does
not run in this skill, but the user can invoke `/research-manager` at end of turn to
also write the matching session-record entry.

---

## `add-claim` / `add-heuristic` / `add-concept` / `add-constraint`

**Args**: `<content> [--provenance <p>] [--bound-to <N{XX},N{YY}>] [--tags t1,t2]`

These stage a new observation in `staging/observations.yaml` with the matching
`potential_type`. The observation stays staged until you call `crystallize`.

**Reads**: `staging/observations.yaml` (next `O{XX}` id).

**Writes**: appends an observation entry:

```yaml
  - id: O{XX}
    timestamp: "<YYYY-MM-DDTHH:MM>"
    provenance: <provenance>
    content: "<content>"
    context: "<derived from $ARGUMENTS or last user turn — one line>"
    potential_type: claim | heuristic | concept | constraint
    bound_to: [<N{XX}>, ...]   # may be empty
    promoted: false
    promoted_to: null
    crystallized_via: null
    stale: false
```

`add-claim` enforces that the `content` reads as a falsifiable assertion. If it doesn't
(e.g. "we should try X" — that's an action, not a claim), warn the user:

```
[ara-manager] Warning: content does not read as a falsifiable claim. 
Consider using `/ara-manager log decision` if this is a choice, or 
rephrase to a falsifiable assertion (e.g. "X achieves Y under conditions Z").
```

The warning does NOT block the staging — premature rejection is worse than staged
vagueness; the user can rephrase before `crystallize`.

---

## `crystallize` — Promote a staged observation

**Args**: `<O{XX}> --via <signal> [--provenance <p>]`
Signal ∈ `affirmation | abandonment | resolution | commitment`.

**Reads**: the observation's `content`, `context`, `potential_type`, `bound_to`,
`provenance`; the target layer file (e.g. `logic/claims.md`) to find the next `C{XX}` /
`H{XX}` id.

**Writes**:
- New typed entry in the target layer file (per the research-manager schema).
- Update the observation: `promoted: true`, `promoted_to: <layer>:<id>`, `crystallized_via: <signal>`.

**Closure signal semantics** (the signal name must match what actually happened):

| Signal | Use when |
|--------|----------|
| `affirmation` | User explicitly endorsed the observation this turn ("yes", "confirmed", "ship it", "let's go with X"). **Upgrades provenance: `ai-suggested` → `user-revised` (or `user` if reproduced verbatim).** |
| `abandonment` | The observation's topic has had no events for the last 5 turns (default k=5 per the ARA closure-signal taxonomy) AND `open_threads` does not reference it. |
| `resolution` | An experiment in `bound_to` produced a result and the user commented on it. **If the result refutes the observation, crystallize to a `dead_end` node in the tree, NOT to a claim.** |
| `commitment` | A downstream artifact now depends on it: a decision node cites it, a config got fixed, code was merged, or a subsequent claim cites it. |

**Default to non-promotion.** If `--via` is omitted, ask the user which signal applies.
If the user is uncertain, abort:

```
[ara-manager] Refusing to crystallize without a clear closure signal. 
Specify --via affirmation|abandonment|resolution|commitment.
```

Crystallization requires the observation to be promoted to the correct layer:

- `potential_type: claim` → `logic/claims.md` as `C{XX}` (next claim id)
- `potential_type: heuristic` → `logic/solution/heuristics.md` as `H{XX}`. If the file
  doesn't exist, create it with `# Heuristics\n`.
- `potential_type: concept` → `logic/concepts.md` as a new `## term\n- **Definition**:` block.
  If the file doesn't exist, create it with `# Concepts\n`.
- `potential_type: constraint` → `logic/solution/constraints.md` as a new `## constraint\n- **Limit**:` block.
- `potential_type: architecture` → `logic/solution/architecture.md`. If absent, create it
  with `# Architecture\n` and append a `## component\n- **Role**:` block.
- `potential_type: unknown` → refuse; ask the user to specify the target type first.

The crystallized entry must include `Crystallized via: <signal>` and
`From staging: O{XX}` as the last two bullet points. The observation itself is NOT
deleted — the staging trail is part of the record.

---

## `advance-claim` — Update a claim's status

**Args**: `<C{XX}> <new-status> [--provenance <p>] [--note "<one-line>"]`
`new-status` ∈ `hypothesis | untested | testing | supported | weakened | refuted | withdrawn | revised`.

**Reads**: `logic/claims.md` (the claim entry).

**Writes**: edits the claim's `- **Status**:` field in place; updates `- **Last revised**:`.

**Allowed transitions** (from the research-manager SKILL.md):

```
hypothesis ──► testing ──► supported
     │            │            ▲
     │            └──► weakened┘
     ├────────────────► refuted    (terminal, empirical)
     ├────────────────► withdrawn  (terminal, non-empirical)
     └─ any ─────────► revised    (Statement rewritten; reset to testing/hypothesis)
```

- Reject any transition not in this graph (e.g. `supported` → `refuted` is allowed; `refuted` → `supported` is NOT — must go through `revised` first).
- If transitioning to `refuted`, also append a `dead_end` node to `trace/exploration_tree.yaml`
  referencing the claim. If the user did not provide enough info to fill `hypothesis`,
  `failure_mode`, and `lesson` on the dead_end, ask.
- Note: this path is distinct from `crystallize --via resolution` to a `dead_end` — that
  path starts from a staged `O{XX}` observation in `staging/observations.yaml`; this
  path starts from an existing `C{XX}` claim in `logic/claims.md`. Both produce a
  `dead_end` node in the trace tree, but they are different entry points.
- `--note` is recorded in the session record's `logic_revisions:` block; it is NOT written
  into the claim file.

**One-step transitions preferred.** Jumping `hypothesis` → `supported` in a single call
requires BOTH (a) a logged experiment with a result that the user has commented on in
this turn, AND (b) the user has explicitly affirmed the result interpretation
(`--note` recording that affirmation). The empirical-resolution signal is primary; the
verbal affirmation is the trigger to call `advance-claim` at all. Without the logged
experiment, refuse and suggest advancing to `testing` first.

**Never demote `supported` → `weakened`** on a single new event. Instead, suggest
appending a contradiction flag and letting the user adjudicate.

---

## `revise-claim` — Rewrite a claim's content

**Args**: `<C{XX}> [--statement "<new>"] [--rationale "<new>"] [--provenance <p>] [--note "<why>"]`

**Reads**: the current claim entry.

**Writes**: edits the `- **Statement**:` and/or `- **Rationale**:` fields in place;
sets `- **Last revised**:`; sets `Status` to `revised` (transition marker — see advance-claim).

**Rules**:
- The new `Statement` MUST remain a falsifiable assertion. If the rewrite makes it
  un-falsifiable, refuse and warn.
- The `Falsification criteria` field is preserved unless `--falsification` is passed.
- `- **Last revised**:` is updated to today.
- A one-line revision record is written to the latest session's `logic_revisions:` block.

---

## `validate` — Seal Level 1 (structural validation)

**Args**: `[--dir <path>]` (default `./ara/`).

**Reads**: every file in the artifact directory.

**Writes**: a `validation_report.md` at the artifact root (or stdout if `--stdout`).

Checks (run all; print a pass/fail line per check, then a summary):

**Directory & file presence**:
1. `PAPER.md` exists, has YAML frontmatter with `title`, `authors|authors_empty`,
   `year`, `claims_summary`.
2. `logic/problem.md`, `logic/claims.md`, `logic/concepts.md`, `logic/experiments.md`,
   `logic/related_work.md` all exist and are non-empty.
3. `logic/solution/constraints.md` exists and is non-empty.
4. `src/environment.md` exists and is non-empty.
5. `trace/exploration_tree.yaml` exists and parses as YAML.
6. `evidence/README.md` exists.
7. `staging/observations.yaml` exists and parses as YAML.

**Cross-layer binding**:
8. Every claim's `Proof:` references an experiment ID that exists in `logic/experiments.md`.
9. Every experiment's `Verifies:` references a claim ID that exists in `logic/claims.md`.
10. `trace/exploration_tree.yaml` `evidence:` fields referencing `C{XX}` resolve to claims.
11. Heuristic `Code ref:` paths exist in `src/` (only if heuristics exist AND `src/` has files).

**Provenance hygiene**:
12. Every claim has a `Provenance:` field with one of the four ARA values
    `user | ai-suggested | ai-executed | user-revised` (paper P2).
13. Every claim has a `Falsification criteria:` field.

**Exploration tree hygiene**:
14. Tree nodes declare `support_level: explicit` or `support_level: inferred`.
15. No `dead_end`/`pivot` node has empty `lesson` / `trigger` (warn, do not fail).

**Self-consistency**:
16. `PAPER.md` `claims_summary` count matches the number of `## C{XX}:` blocks in `logic/claims.md`.
17. IDs are unique within their file (no two `C{XX}` with the same number).

Print the result:

```
[validate] Seal Level 1: PASS  (17/17 checks)
or
[validate] Seal Level 1: FAIL  (14/17 checks)
  F08: Claim C03 "Proof: [E99]" — E99 not in logic/experiments.md
  F11: Heuristic H02 "Code ref: src/foo.py" — file not found
  F16: PAPER.md claims_summary lists 5, but logic/claims.md has 4 claim blocks.
```

For more thorough validation (figure-vs-markdown, screenshot presence, etc.), first
run the `compile` command on the artifact to regenerate state, then re-run `validate`.

---

## `review` — Delegate to rigor-reviewer (Seal Level 2)

**Args**: `[--dir <path>]` (default `./ara/`).

**Action**: Print the call to the user, do NOT execute it directly. The level-2 review
requires deep semantic analysis and is delegated to the dedicated `rigor-reviewer` skill.

Print:

```
[ara-manager] For Seal Level 2 (semantic epistemic review), invoke:
  /rigor-reviewer $ARA_DIR
The review will produce a `level2_report.json` at the artifact root with scores
across six dimensions (evidence relevance, falsifiability, scope calibration,
argument coherence, exploration integrity, methodological rigor).
```

If the user asks to "do the review" without invoking the skill directly, run the level-2
check yourself only if the artifact is small (<10 claims, <20 evidence files); otherwise,
insist on `/rigor-reviewer` for a thorough audit.

---

## `compile` — Deep-read inputs, epistemic extraction, generate artifact (thorough)

**Args**: `<path-or-url> [...] [--output <dir>] [--crystallize] [--rubric <path>]`

**Reads**: one or more input files/directories (markdown, text, structured docs);
existing ARA project state for dedup.

**Writes**: staged observations; optionally crystallized entries + validation report.

**The difference between `compile` and `update with`:**

| Aspect | `update with` | `compile` |
|--------|---------------|-----------|
| Depth | 1 pass — read → extract → stage | 3 passes — inventory → classify → cross-ref → stage → optional crystallize |
| Dedup | Light (check existing observation IDs) | Thorough (semantic dedup against claims, concepts, heuristics) |
| Crystallization | Never auto-crystallizes | Optional `--crystallize` flag promotes ready observations |
| Output | Stages observations only | Stages + optionally crystallizes + runs validation |
| PDF handling | Skips with note | Mentions as skipped; suggests manual extraction |
| Use case | "I just finished writing a doc, update ARA quick" | "I have a batch of research outputs, rebuild ARA state" |

### Protocol (3 passes)

**Pass 1 — Inventory**: Read all input files. Extract every distinct factual claim,
design decision, experimental outcome, concept definition, constraint, and heuristic.
For each, capture: source file, excerpt, type.

**Pass 2 — Classify + Dedup**: For each extracted fact, determine `potential_type`
(claim / concept / constraint / heuristic / experiment / decision). Cross-reference
against existing ARA state:
- If the fact matches an existing claim/concept/etc. (semantic similarity), skip with note
- If the fact refines an existing entry, suggest a revision (do NOT revise without user confirmation)
- If the fact is novel, prepare for staging

**Pass 3 — Stage + optional Crystallize**: Append novel observations to
`staging/observations.yaml`. If `--crystallize` is set, also check each staged
observation for a clear closure signal (experiment completed, user affirmed). For
those with clear signals, run `crystallize` automatically with signal=`resolution`
(for experiments) or `commitment` (for code changes/configs). Report what was
staged, what was crystallized, and what was skipped.

After all passes, run `validate` (Seal Level 1) on the artifact and print the result.

### `compile` (no args)

If no path is given, scan the current directory for common input patterns:
`docs/`, `*.md`, `*.yaml`, `README*`. Print what was found and stage results.

### Output summary

```
[ara-manager] compile docs/ 
  Pass 1: 12 facts extracted from 3 files
  Pass 2: 8 novel, 3 duplicates, 1 refinement suggested
  Pass 3: 8 observations staged (4 claims, 2 concepts, 1 constraint, 1 heuristic)
  Validate: Seal Level 1 — PASS (17/17)
```

---

## `improve-arch` — Improve `src/` architecture (delegates to improve-codebase-architecture)

**Args**: `[--dir <path>]` (default `./ara/`), `[--scope kernel|repo|all]` (default `all`),
`[--focus <module-glob>]` (e.g. `src/kernel/gnn*`), `[--no-explore]` (skip the
Explore subagent; useful for tiny projects).

**Action**: Print the call to the user. Architecture analysis is a deep
exploration/refactoring task delegated to the dedicated
`improve-codebase-architecture` skill. Do NOT execute it inline — even for small
projects, the skill's Explore subagent + grilling loop is the right shape.

**Why this lives in `ara-manager`**: the ARA `src/` layer has two modes
declared in `PAPER.md` frontmatter as `src_mode: kernel | repo` (paper §A.2).
`kernel` mode keeps only the algorithmic core with typed I/O signatures; `repo`
mode keeps the full implementation with an `index.md` manifest mapping source
files to ARA components (claims, heuristics, architecture modules). In either
mode, the `src/` layer is exactly the kind of code that benefits from
**deepening opportunities** — turning shallow pass-through modules into
high-leverage interfaces, surfacing real seams (two adapters), and improving
testability/AI-navigability. Routing the request to the dedicated skill
ensures consistent vocabulary (depth, seam, deletion test) and the same
process (Explore → candidates → grilling).

Print:

```
[ara-manager] For src/ architecture improvement, invoke:
  /improve-codebase-architecture $ARA_DIR/src [--scope <kernel|repo|all>]

The skill will:
  1. Read PAPER.md src_mode + logic/solution/ + relevant ADRs in scope.
  2. Use the Explore subagent to walk src/ and surface deepening opportunities
     (shallow modules, missing seams, untested interfaces, tightly-coupled
     clusters that fail the deletion test).
  3. Present candidates using domain vocabulary from logic/solution/concepts.md
     and architecture vocabulary (depth, seam, adapter, locality, leverage).
  4. Drop into a grilling loop on whichever candidate you pick.

For kernel-mode projects, the kernel's typed I/O signatures are the test
surface — refactors should preserve them. For repo-mode projects, the
index.md manifest must be updated as src/ files are deepened.
```

**Mode-specific notes** the user should know:
- **`src_mode: kernel`**: refactoring should keep the kernel small (1–2 orders
  of magnitude below the full repo). Don't propose splitting the kernel
  further unless the user wants to.
- **`src_mode: repo`**: any new module, file move, or interface change requires
  updating `src/index.md` to re-bind the file to its ARA components. Flag this
  as a side effect of every candidate.
- If `PAPER.md` has no `src_mode` field, ask the user which mode applies
  before delegating — it changes which deepening patterns are appropriate.

**Optional post-step**: after the user accepts a deepening proposal and the
refactor lands, log it as a `pivot` in `trace/exploration_tree.yaml` (so the
"original rationale" is preserved) and, if the refactor invalidates a
heuristic, append a contradiction flag to the heuristic's `C{XX}` and let
the user adjudicate at the next `briefing`.

---

## `organize` — Multi-agent ARA maintenance loop

**Args:** `<sub-mode> [args...]`

Sub-modes:

| Sub-mode | What it does |
|----------|-------------|
| `scout` | Read-only health report of current ARA state |
| `extract <path>` | Scan files/directories → stage new observations |
| `crystallize` | Propose crystallization candidates from staging |
| `audit` | Analyze claims for status advancement opportunities |
| `clean` | Stale flags, dedup, validate |
| `all` | Full pipeline: scout → extract → review → respond → execute → verify |
| `daily` | L1 maintenance: scout + housekeep + validate, write report to `ara/daily/` |
| `test` | Run all phases with test fixture — verify full pipeline produces expected output |

Dispatch on `args[0]` after extracting `subcommand=organize`.

**What it does:** Launches a multi-agent loop engineering pipeline:

| Phase | Agent | Model | Role |
|-------|-------|-------|------|
| Scout | Scout | Haiku | Read-only health report of ARA state |
| Extract | Extractor | Haiku | Read docs/ → stage novel observations |
| Review | Crystallizer | Haiku | Propose crystallization candidates |
| Review | Claim Auditor | Haiku | Propose claim status advancements |
| Review | Reviewer | Opus + nature-reviewer | Academic-level quality gate |
| Respond | Responder | Sonnet + nature-response | Formal replies + remediation dispatch |
| Execute | Specialized agents | Haiku | Apply approved changes |
| Verify | Validator | Haiku | Structural validation (Seal Level 1) |

**Reads:** Full ARA project state (`ara/logic/`, `ara/staging/`, `ara/trace/`), targeted docs/ paths for `extract`.

**Writes:** Depends on sub-mode:
- `scout`, `audit` — reads only
- `extract` — appends to `ara/staging/observations.yaml`
- `crystallize`, `audit`, `all` — writes to `ara/logic/` after Opus review approval + user confirmation
- `clean` — sets `stale: true` flags in staging, runs validate
- `daily` — writes report to `ara/daily/YYYY-MM-DD.md`

**Implementation:** This is a **delegating command** — do NOT implement the logic inline. Instead, invoke the Workflow tool with the `scriptPath` pointing to the bundled workflow file.

The workflow engine at **`~/.claude/skills/ara-manager/workflows/ara-organize.js`** handles sub-agent dispatch (Scout, Extract, Review with Opus reviewer, Respond with Sonnet responder, Execute, Verify). This file ships with the skill — do NOT create a separate copy.

**Architecture note — parallel dispatch:** The bundled workflow uses **sequential** sub-agents (one per phase, full context). For projects with large report sets or many claims, prefer a **parallel dispatch** variant that fans out N independent sub-agents per phase using `Promise.all()` and `pipeline()`, then merges results. Each sub-agent gets a shorter, focused context slice — this scales better and avoids context window pressure. A parallel-dispatch template is at `~/.claude/skills/ara-manager/workflows/ara-organize-parallel.js`; copy it to your project's `.claude/workflows/ara-organize.js` and adjust paths.

For `extract` sub-mode, pass the target path: `{scriptPath: "~/.claude/skills/ara-manager/workflows/ara-organize.js", args: {focus: "extract", mode: "extract", paths: ["<path>"]}}`.

On invocation, print the dispatch message then call:

```javascript
Workflow({
  scriptPath: "~/.claude/skills/ara-manager/workflows/ara-organize.js",
  args: {focus: "<sub-mode>", mode: "<sub-mode>"}
})
```

Dispatch message:

```
[ara-manager] organize <sub-mode> — dispatching multi-agent maintenance loop.
Workflow: ~/.claude/skills/ara-manager/workflows/ara-organize.js
```

For `daily` mode specifically:

```
[ara-manager] organize daily — running L1 maintenance.
Report will be written to ara/daily/<date>.md.
```

**Examples:**
- `organize scout` — read-only health check
- `organize extract docs/handoffs/` — scan handoffs for new observations
- `organize audit` — review claims for advancement
- `organize clean` — stale flags + validate
- `organize all` — full pipeline
- `organize daily` — scheduled L1 maintenance (daily 23:30 cron)
- `organize test` — run full pipeline against test fixture, verify output

---

## Per-Command Procedure

For every command:

1. Parse `$ARGUMENTS` → `subcommand` + `args`.
2. Resolve project directory (`--dir` flag → `./ara/` → scan for `PAPER.md`).
3. For commands other than `init` / `help`, confirm an ARA project exists.
4. Read target files (id allocation, schema conformance, freshness check).
5. Apply the command's writes.
6. Run a consistency pass on touched files (e.g., new claim → update `claims_summary` in `PAPER.md`).
7. Print the one-line summary. For long output (status, briefing, tree), print the full
   dashboard.

## Rules

1. **Honor layer mutability.** `logic/` overwrites in place; `trace/`, `staging/`,
   `evidence/` are append-only (you may append entries; never rewrite or delete prior
   entries).
2. **Never invent IDs.** Read the target file first, find the highest existing prefix,
   increment.
3. **Never silently overwrite contradictions.** If a new event contradicts a crystallized
   claim, refuse to advance-status, flag both, and tell the user to adjudicate.
4. **Default to non-promotion / no-change.** Crystallization requires a closure signal;
   `revise-claim` and `advance-claim` require explicit user direction.
5. **Provenance is conservative.** Default to `ai-suggested` when uncertain. Never
   auto-upgrade to `user-revised` without an explicit user revision this turn.
6. **Terminal states need explicit triggers.** `refuted` and `withdrawn` are terminal.
   To revive a terminal claim: run `revise-claim` first to rewrite the `Statement`
   (which sets `Status: revised` as a transition marker), then `advance-claim` to set
   the new status (`hypothesis` or `testing`). Do NOT advance directly from `refuted`
   → `supported` — the `revised` intermediate is required.
7. **Self-consistency.** After every write, check that the change doesn't break
   cross-layer bindings (claim count, experiment refs, etc.). Fix immediately.
8. **Be terse in success output.** One line is enough. Verbose output is reserved for
   `status`, `briefing`, `tree`, and `validate`.
9. **Skip empty writes.** If a command would have no effect (e.g. `log decision` with
   no description), print a usage hint and exit.
10. **Delegate expertise-heavy work.** Level-2 review and architecture analysis belong to their
    dedicated skills (`/rigor-reviewer`, `/improve-codebase-architecture`); this skill
    orchestrates, not re-implements. `compile` and `update` are native — no delegation needed.

## See also

- `references/commands.md` — exhaustive per-command spec with edge cases
- `references/ara-quick-ref.md` — ARA structure / schema quick reference
- The ARA standard: https://github.com/Orchestra-Research/Agent-Native-Research-Artifact
- Companion skills: `/research-manager` (per-turn epilogue), `/rigor-reviewer` (Seal Level 2 epistemic audit)
