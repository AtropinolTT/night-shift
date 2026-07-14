# ARA Project Manager

**A command-based project management interface for [Agent-Native Research Artifacts (ARA)](https://github.com/Orchestra-Research/Agent-Native-Research-Artifact).**

ARA turns a research project from a linear narrative (PDF) into a **machine-executable knowledge package** — four interlocking layers that AI agents can navigate, reproduce, and extend without rediscovering every dead end.

This skill provides the **unified command interface** to an ARA project: initialize it, query its state, log research events, add claims and heuristics, crystallize staged observations, validate structural integrity, and run epistemic reviews.

---

## Quick Start

### Prerequisites

- **Claude Code** (or compatible AI coding assistant with skill support)
- A research project you want to manage

### Installation

Copy the `ara-manager` skill into your Claude Code skills directory:

```bash
cp -r ara-manager ~/.claude/skills/
```

Alternatively, symlink for live updates:

```bash
ln -s $(pwd)/ara-manager ~/.claude/skills/
```

Once installed, invoke in Claude Code:

```
/ara-manager init "My Research Project" --domain "NLP" --keywords "transformer,attention"
```

### Your First Project

```bash
# Create a new ARA project
/ara-manager init "My Research Project" --domain "NLP"

# Check status
/ara-manager status

# Log a research decision
/ara-manager log decision "Chose AdamW over SGD" --alternatives "SGD,RMSProp"

# Add a falsifiable claim
/ara-manager add-claim "The model achieves >90% accuracy on dataset X" --tags perf

# Promote a staged claim once confirmed
/ara-manager crystallize O03 --via affirmation

# Advance a claim's status when evidence arrives
/ara-manager advance-claim C03 supported --note "E05 result confirms"

# Run structural validation
/ara-manager validate

# Full epistemic review
/ara-manager review
```

---

## Commands at a Glance

| Command | Purpose |
|---------|---------|
| `init [title]` | Create a new ARA project at `./ara/` |
| `status` | Project dashboard: claim statuses, staged observations, open threads |
| `briefing` | Full briefing: where you left off, stale observations, pending suggestions |
| `tree` | Print the exploration DAG |
| `help` | Show all commands with examples |
| `log <type> <desc>` | Log a journey fact (decision / experiment / dead_end / pivot / question) |
| `add-claim <text>` | Stage a new falsifiable claim |
| `add-heuristic <text>` | Stage a new implementation heuristic |
| `add-concept <term>` | Stage a new term definition |
| `add-constraint <text>` | Stage a new boundary condition |
| `crystallize O{XX}` | Promote a staged observation into `logic/` on a closure signal |
| `advance-claim C{XX} <status>` | Update a claim's status (e.g. `testing` → `supported`) |
| `revise-claim C{XX}` | Rewrite a claim's statement / rationale |
| `validate` | Run Seal Level 1 structural validation (17 checks) |
| `review` | Run Seal Level 2 epistemic review |
| `compile <input>` | Deep-read inputs, extract knowledge, stage observations |
| `update with <path>` | Lightweight scan of external docs → stage observations |
| `organize <mode>` | Multi-agent maintenance loop (scout / extract / crystallize / audit / clean / all / daily) |
| `improve-arch` | Analyze and deepen `src/` architecture |

---

## The ARA Structure

```
ara/
  PAPER.md                          # Root manifest + layer index
  logic/                            # What & Why (mutable)
    problem.md                      #   Observations → gaps → key insight
    claims.md                       #   Falsifiable claims (C01, C02, …)
    concepts.md                     #   Formal term definitions
    experiments.md                  #   Declarative experiment plans
    related_work.md                 #   Typed dependency graph
    solution/                       #   Constraints, heuristics, architecture
  src/                              # How (concrete artifacts)
    environment.md                  #   Reproducibility (deps, hardware, seeds)
    configs/                        #   Configuration files
    execution/                      #   Run scripts and pipelines
    data/                           #   Datasets and processed results
  trace/                            # Journey (append-only)
    exploration_tree.yaml           #   Research DAG (questions → decisions → experiments → dead-ends)
    pm_reasoning_log.yaml           #   Manager's organizational decisions
    sessions/                       #   Per-day session records
  evidence/                         # Raw proof (append-only)
    README.md                       #   Index mapping evidence to claims
    tables/                         #   Data tables (md + png)
    figures/                        #   Visual results (md + png)
    proofs/                         #   Mathematical derivations
  staging/                          # Crystallization buffer (append-only)
    observations.yaml               #   Raw observations awaiting closure
```

### Layer Mutability

| Layer | Mutability | What It Holds |
|-------|-----------|---------------|
| `logic/` | **Mutable** — rewritten in place | Current best understanding |
| `src/` | Mutable | Code, configs, environment |
| `trace/` | **Append-only** | The journey record |
| `evidence/` | **Append-only** | Raw proof files |
| `staging/` | **Append-only** | Observations pending crystallization |

---

## Command Details

### `init` — Initialize a Project

Creates the full ARA directory tree with seed files. Refuses to overwrite an existing project.

```
/ara-manager init "Protein-Ligand Binding with GNNs" \
    --domain "computational chemistry" \
    --keywords gnns,drug-discovery
```

### `log` — Log a Journey Fact

Records research events directly to the exploration tree (append-only). Types:

| Fact Type | Use When |
|-----------|----------|
| `decision` | You chose X over Y |
| `experiment` | You ran an experiment with a result |
| `dead_end` | An approach failed |
| `pivot` | You changed direction |
| `question` | An open question to revisit |

```
/ara-manager log experiment "Trained GNN with 3 layers — 0.87 ROC-AUC on ChEMBL"
/ara-manager log dead_end "Tried LayerNorm before attention — diverged"
/ara-manager log pivot "Switched from learned to fixed positional encodings"
```

### `add-claim`, `add-heuristic`, `add-concept`, `add-constraint`

These stage new observations in `staging/observations.yaml`. They do NOT write to `logic/` directly — crystallization is a separate step.

```
/ara-manager add-claim "Our model achieves >0.85 ROC-AUC on the ChEMBL benchmark"
/ara-manager add-heuristic "Use cosine LR schedule with 5-epoch warmup"
/ara-manager add-concept "graph-aware pooling" \
    --def "Aggregates node features by edge type"
/ara-manager add-constraint "Training must complete within 8 hours on a single A100"
```

### `crystallize` — Promote an Observation

Requires a **closure signal** — evidence that the observation is ready to move from staging into the logic layer:

```
/ara-manager crystallize O03 --via affirmation     # user confirmed it
/ara-manager crystallize O07 --via resolution       # experiment completed
/ara-manager crystallize O12 --via commitment       # code/config depends on it
/ara-manager crystallize O15 --via abandonment      # no activity, not referenced
```

When crystallizing to a claim, it creates a `C{XX}` entry in `logic/claims.md`. The original observation stays in staging with `promoted: true` (the staging trail is part of the record).

### `advance-claim` — Update Claim Status

Allowed transitions:

```
hypothesis ──► testing ──► supported
     │            │            ▲
     │            └──► weakened┘
     ├────────────────► refuted    (terminal)
     ├────────────────► withdrawn  (terminal)
     └─ any ─────────► revised    (transition marker)
```

```
/ara-manager advance-claim C03 testing --note "E05 launched, results pending"
/ara-manager advance-claim C03 supported --note "E05 result 92.3% confirms claim"
```

### `validate` — Seal Level 1

Runs 17 structural checks: file presence, cross-layer bindings, provenance hygiene, tree hygiene, and self-consistency.

```
/ara-manager validate
```

### `review` — Seal Level 2

Delegates to the `rigor-reviewer` skill for deep semantic epistemic review across six dimensions.

```
/ara-manager review
```

### `compile` — Deep Extraction

3-pass protocol: inventory → classify/dedup → stage.

```
/ara-manager compile docs/                     # scan docs for extraction
/ara-manager compile docs/ --crystallize       # auto-crystallize ready observations
```

### `update` — Lightweight Scan

```
/ara-manager update with docs/handoffs/        # scan files → stage observations
/ara-manager update claims                     # review claim statuses
/ara-manager update obs                        # review staged observations
```

### `organize` — Multi-Agent Maintenance

Launches a multi-agent pipeline for automated ARA maintenance:

```
/ara-manager organize scout                    # read-only health report
/ara-manager organize extract docs/            # extract new observations
/ara-manager organize crystallize              # propose crystallization candidates
/ara-manager organize audit                    # propose claim status changes
/ara-manager organize clean                    # stale flags + validate
/ara-manager organize all                      # full pipeline
/ara-manager organize daily                    # L1 scheduled maintenance
```

---

## Best Practices

### 1. Stage Before Crystallizing

Always stage observations first (`add-claim`, `add-heuristic`, etc.) and crystallize only when a closure signal fires. This preserves the evidence trail and prevents premature commitment.

### 2. Write Falsifiable Claims

A good claim is testable:

```
✅ "The model achieves >90% accuracy on dataset X under 100k training samples"
❌ "The model works well"
❌ "We should try a different approach" (this is a decision, not a claim)
```

### 3. Use Provenance Consistently

Four provenance values — pick the right one:

| Value | Use When |
|-------|----------|
| `user` | The user said it in first person |
| `ai-suggested` | The AI proposed it; user hasn't confirmed yet **(safe default)** |
| `ai-executed` | The AI performed the action (ran experiment, generated result) |
| `user-revised` | The AI proposed, the user edited it |

### 4. Honor Mutability Rules

- **Logic files** (`logic/`) — edit in place (current best understanding)
- **Trace, staging, evidence** — only append, never delete or rewrite

### 5. One-Step Transitions Preferred

Jump `hypothesis` → `testing` → `supported`, not `hypothesis` → `supported` in one leap without evidence.

### 6. Never Invent IDs

Read the target file first to find the highest existing ID, then increment. Never guess.

### 7. Cross-Layer Consistency

After every write, ensure cross-layer bindings remain valid:
- Claim `Proof:` references must exist in `experiments.md`
- Experiment `Verifies:` references must exist in `claims.md`
- `PAPER.md` `claims_summary` count must match claim blocks count

### 8. Default to Non-Promotion

Crystallization requires a clear closure signal. When uncertain, keep the observation staged.

---

## How It Fits the ARA Ecosystem

| Skill | Purpose |
|-------|---------|
| **`/ara-manager`** | On-demand project operations (you are here) |
| **`/compiler`** | One-shot: papers → repos → logs → complete ARA artifact |
| **`/research-manager`** | Per-turn epilogue: records research events with provenance |
| **`/rigor-reviewer`** | Seal Level 2: deep semantic epistemic review |
| **`/improve-codebase-architecture`** | Analyzes and deepens `src/` architecture |

---

## Files

| File | Description |
|------|-------------|
| `SKILL.md` | The skill specification (machine-readable for Claude Code) |
| `README.md` | This file — open-source documentation |
| `LICENSE` | MIT License |
| `references/commands.md` | Exhaustive per-command reference with edge cases |
| `references/ara-quick-ref.md` | ARA structure / schema quick reference |
| `workflows/ara-organize.js` | Backend engine for the `organize` multi-agent pipeline |
| `tutorial.html` | Interactive HTML tutorial |

## Reference

- [ARA Standard on GitHub](https://github.com/Orchestra-Research/Agent-Native-Research-Artifact)
- The companion paper: [arXiv:2604.24658](https://arxiv.org/abs/2604.24658)
- ARA skill family: `/compiler`, `/research-manager`, `/rigor-reviewer`

---

## License

MIT — see [LICENSE](LICENSE).
