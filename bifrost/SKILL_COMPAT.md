# Bifrost Skill Bridge — Verified Skill Compatibility

Feature 5 of 7: Skill bridge that loads, parses, and executes companion skills
through argument substitution (`$0`/`$NAME`) with zero shell exec.

---

## Verified Skills (9)

Each skill below has been manually audited by reading its `SKILL.md` source.
Verification criteria:

| Criterion | Requirement |
|---|---|
| Shell exec (`!`cmd``) | MUST be NONE — zero inline shell execution |
| Frontmatter | Standard YAML frontmatter with `name` and `description` |
| Dangerous patterns | No file deletion, no system modification directives |
| Argument substitution | Compatible with Bifrost `$ARGUMENTS` / `$0` substitution |

### Compatibility Table

| # | Name | Category | Verified Features | Limitations | Shell Exec | Status |
|---|---|---|---|---|---|---|
| 1 | `caveman` | Communication / Style | Token-efficient communication (~75% reduction). Persistence across turns. Auto-clarity exception for security warnings and destructive ops. Fragment-based response patterns. Self-contained: no external dependencies. | Style override only — must be explicitly disabled (`stop caveman`). Does not modify tool behavior, only prose output. | NONE | ✅ Verified |
| 2 | `diagnose` | Debugging / Engineering | 6-phase disciplined debugging loop: feedback loop construction (10 methods), reproduce, hypothesize (3-5 falsifiable), instrument (one variable at a time), fix + regression test, cleanup + post-mortem. Domain glossary and ADR awareness. | Methodology only — no automated debugging. Requires user interaction for hypothesis confirmation. References external skills (`improve-codebase-architecture`) for architectural recommendations. | NONE | ✅ Verified |
| 3 | `handoff` | Session Management | Conversation compaction to handoff document. Suggested skills section. Sensitive info redaction. Context-aware via `argument-hint`. Writes to OS temp directory (not workspace). | Documentation generation only — no state transfer. Relies on existing artifacts (PRDs, plans, ADRs) for references. | NONE | ✅ Verified |
| 4 | `grill-me` | Design / Planning | Relentless design interview — walks decision tree branches one question at a time. Recommends answers per question. Falls back to codebase exploration when answerable from code. | Interactive only — requires user engagement. No automated design generation. Question output depends on user's plan quality. | NONE | ✅ Verified |
| 5 | `ara-manager` | Research / Project Management | Full ARA project lifecycle: init, status, briefing, tree visualization, logging (decisions/experiments/dead-ends/pivots/questions), claim management (add/crystallize/advance/revise), structural validation (Seal Level 1, 17 checks), epistemic review delegation (Seal Level 2), compilation from external inputs, architecture improvement. 18 commands. References companion skills: `rigor-reviewer`, `improve-codebase-architecture`, `compiler`. | Complex skill — 892 lines. Uses `$ARGUMENTS` and `$ARA_DIR` variable substitution (Bifrost-compatible). Delegates to external skills for review/architecture. `allowed-tools` restricts to specific Bash patterns. `organize` sub-command delegates to an external JavaScript workflow file. | NONE | ✅ Verified |
| 6 | `nature-polishing` | Academic Writing | Dynamic routing to static fragments based on detected axes (paper_type, section, language, journal). 5-step routing protocol: manifest load, axis detection, fragment load, polish with priority cascade, on-demand reference access. LaTeX layout/typesetting fix mode (float placement, page density, multi-panel arrangement). Covers: Nature/Nat-Comms/generic journals, research/methods/hypothesis/algorithmic/review paper types, Chinese-to-English translation. | Static fragment files must be present alongside SKILL.md (under `static/` and `references/`). Requires user-provided draft text. Journal-specific patterns limited to Nature-family journals. | NONE | ✅ Verified |
| 7 | `feishu-kb` | Knowledge Management | Three-mode operation (qa/maintain/update) aligned with Karpathy LLM Wiki pattern. QA: 4-folder scoped search, PDF parsing, citation following (5-layer), comparison detection. Maintain: dedup, lint, frontmatter backfill, KG scaffold, KB log append, IM reporting. Update: 4-source paper search (NCBI/CrossRef/Semantic/arXiv) + RSS polling, dedup, journal filtering, paper doc creation. Subagent architecture (librarian/maintainer/collector). | Requires Feishu API credentials (lark-cli OAuth). Requires conda environment `marker` with pdfplumber + pymupdf. External lark-cli npm package. Write operations use lark-cli — the skill documents these as Bash commands in code blocks, not inline exec. Self-check script must pass before any operation. Karpathy schema features (enforcement, auto-KG) deferred to future versions. | NONE | ✅ Verified |
| 8 | `night-shift` | Job Scheduling | DeepSeek V4 pricing-aware job scheduler. Commands: submit, status, run, hold, retry, config. Deterministic scripts (check-window, estimate-cost, parse-queue). Model routing matrix (window x model-hint x job-type). Dispatch protocol: pre-flight, concurrency guard (`<!-- dispatching -->` annotation), model selection, execute (Workflow tool), post-dispatch. Autonomy levels L2 (assisted) and L3 (unattended). Cron-based scheduled dispatch with teardown/recreate on config change. Rationalization counter-table for anti-patterns. | Requires `~/.claude/night-shift/` config files (pricing.json, config.json, state.json). Scripts under `scripts/` must be present. Workflow tool used for dispatch — JavaScript functions reference `agent()` and `Workflow()` which are tool-call syntax, not shell exec. Cron integration uses `CronCreate`/`CronList`/`ScheduleWakeup` tool calls. | NONE | ✅ Verified |
| 9 | `ai-galaxy` | Cloud / Infrastructure | AI Galaxy (智星云) GPU cloud management. SSH/SFTP connections via Python paramiko (`ssh_connector.py`). Instance management via REST API (list, status, start/stop, create, resize, renew). Training job submission using `invoke_shell()` for background processes. Job monitoring via `exec_command()`. File transfer via SFTP + SCP. GPU monitoring (`nvidia-smi`). Screen-based long-running tasks. Docker GPU jobs. Troubleshooting guides for SSH, instance, disk, module, and training issues. | Requires user-provided credentials: instance IP, SSH port, password. Requires Python paramiko library. `ssh_connector.py` helper at `<skill-base>/scripts/`. All shell commands are documented as examples in code blocks — no inline exec. REST API requires AccessKey signature authentication. | NONE | ✅ Verified |

---

## Verification Summary

All 9 skills pass the Bifrost skill bridge compatibility requirements:

- **Shell exec (`!`cmd``):** NONE — zero skills use inline shell execution syntax
- **Frontmatter:** All use standard YAML frontmatter with `name` and `description`
- **Argument handling:** `ara-manager` uses `$ARGUMENTS`; `handoff` and `night-shift` use `argument-hint`; all are compatible with Bifrost's `$0`/`$NAME` substitution
- **Dangerous patterns:** None found — no file deletion directives, no system modification in skill bodies
- **External dependencies:** Documented per skill (see Limitations column)

### Skill Complexity Distribution

| Complexity | Skills |
|---|---|
| Simple (<50 lines) | `caveman` (49), `handoff` (15), `grill-me` (10) |
| Medium (50-250 lines) | `diagnose` (117), `nature-polishing` (74), `ai-galaxy` (243) |
| Complex (250+ lines) | `ara-manager` (892), `feishu-kb` (417), `night-shift` (448) |

---

## Best-Effort Skills (Remaining 74)

The following skills exist in the workspace but have NOT been verified against Bifrost
compatibility criteria. They are listed here for reference with a `best-effort` status.
Verification would require reading each SKILL.md individually (out of scope for T7.1).

Skills are organized by installation scope:

### User Scope (`~/.claude/skills/`)

| Skill | Category | Best-Effort Status |
|---|---|---|
| `customize-opencode` | Configuration | Not verified |
| `security-research` | Security | Not verified |
| `security-review` | Security | Not verified |
| `dl-tuning-playbook` | Deep Learning / Training | SKILL.md not found in workspace |

### Project Scope — `.claude/skills/`

| Skill | Category | Best-Effort Status |
|---|---|---|
| `alphagenome-single-variant-analysis` | Bioinformatics | Not verified |
| `chembl-database` | Bioinformatics / Database | Not verified |
| `edit-article` | Writing / Prose | Not verified |
| `embl-ebi-ols` | Bioinformatics / Ontology | Not verified |
| `encode-ccres-database` | Bioinformatics / Database | Not verified |
| `git-guardrails-claude-code` | Git / Safety | Not verified |
| `gtex-database` | Bioinformatics / Database | Not verified |
| `improve-codebase-architecture` | Engineering / Architecture | Not verified |
| `literature-search-arxiv` | Academic / Literature | Not verified |
| `literature-search-openalex` | Academic / Literature | Not verified |
| `nature-citation` | Academic Writing | Not verified |
| `nature-figure` | Academic Writing / Visualization | Not verified |
| `nature-reviewer` | Academic Writing / Review | Not verified |
| `nature-writing` | Academic Writing | Not verified |
| `obsidian-vault` | Knowledge Management | Not verified |
| `opentargets-database` | Bioinformatics / Database | Not verified |
| `pdb-database` | Bioinformatics / Database | Not verified |
| `prototype` | Engineering / Design | Not verified |
| `pubchem-database` | Cheminformatics / Database | Not verified |
| `pubmed-database` | Academic / Literature | Not verified |
| `pymol` | Bioinformatics / Visualization | Not verified |
| `quickgo-database` | Bioinformatics / Database | Not verified |
| `reactome-database` | Bioinformatics / Database | Not verified |
| `scaffold-exercises` | Education | Not verified |
| `setup-matt-pocock-skills` | Setup / Configuration | Not verified |
| `setup-pre-commit` | Git / Setup | Not verified |
| `tdd` | Engineering / Testing | Not verified |
| `teach` | Education | Not verified |
| `to-prd` | Engineering / Planning | Not verified |
| `triage` | Engineering / Workflow | Not verified |
| `ubiquitous-language` | Engineering / Design | Not verified |
| `uv` | Python / Setup | Not verified |
| `grill-with-docs` | Design / Planning | Not verified |
| `writing-fragments` | Writing / Prose | Not verified |

### Project Scope — `.agents/skills/`

| Skill | Category | Best-Effort Status |
|---|---|---|
| `alphafold-database-fetch-and-analyze` | Bioinformatics | Not verified |
| `clinical-trials-database` | Bioinformatics / Clinical | Not verified |
| `clinvar-database` | Bioinformatics / Database | Not verified |
| `dbsnp-database` | Bioinformatics / Database | Not verified |
| `design-an-interface` | Engineering / Design | Not verified |
| `ensembl-database` | Bioinformatics / Database | Not verified |
| `foldseek-structural-search` | Bioinformatics / Structural | Not verified |
| `gnomad-database` | Bioinformatics / Database | Not verified |
| `human-protein-atlas-database` | Bioinformatics / Database | Not verified |
| `interpro-database` | Bioinformatics / Database | Not verified |
| `jaspar-database` | Bioinformatics / Database | Not verified |
| `literature-search-biorxiv` | Academic / Literature | Not verified |
| `literature-search-europepmc` | Academic / Literature | Not verified |
| `migrate-to-shoehorn` | Engineering / Testing | Not verified |
| `nature-academic-search` | Academic / Literature | Not verified |
| `nature-data` | Academic Writing | Not verified |
| `nature-paper2ppt` | Academic Writing | Not verified |
| `nature-reader` | Academic Writing / Reading | Not verified |
| `nature-response` | Academic Writing | Not verified |
| `ncbi-sequence-fetch` | Bioinformatics / Sequence | Not verified |
| `openfda-database` | Bioinformatics / Clinical | Not verified |
| `protein-sequence-msa` | Bioinformatics / Sequence | Not verified |
| `protein-sequence-similarity-search` | Bioinformatics / Sequence | Not verified |
| `qa` | Engineering / QA | Not verified |
| `request-refactor-plan` | Engineering / Planning | Not verified |
| `review` | Engineering / Code Review | Not verified |
| `scienceskillscommon` | Shared Library | Not verified |
| `string-database` | Bioinformatics / Database | Not verified |
| `to-issues` | Engineering / Planning | Not verified |
| `ucsc-conservation-and-tfbs` | Bioinformatics / Database | Not verified |
| `unibind-database` | Bioinformatics / Database | Not verified |
| `uniprot-database` | Bioinformatics / Database | Not verified |
| `workflow-skill-creator` | Meta / Skills | Not verified |
| `write-a-skill` | Meta / Skills | Not verified |
| `writing-beats` | Writing / Prose | Not verified |
| `writing-shape` | Writing / Prose | Not verified |
| `zoom-out` | Engineering / Navigation | Not verified |

### Known Non-Compatible Skills (by category)

Bioinformatics/database skills that use MCP tool calls, API keys, or external services
are listed as "best-effort" because they may require:

- API keys (AlphaGenome, ENCODE, OpenTargets, etc.)
- MCP server connections (PubMed, CrossRef, Scopus)
- External tool dependencies (PyMOL, Foldseek)
- Network access to external APIs

These are not necessarily incompatible with Bifrost, but have not been verified.

---

## Methodology

Each of the 9 verified skills was audited by reading its full `SKILL.md` source and
checking for:

1. Inline shell exec patterns (`!`cmd`` or equivalent)
2. YAML frontmatter validity
3. Dangerous file system operations (rm, mv, delete)
4. External API key requirements
5. Argument variable usage
6. Reference file dependencies

Document generated for Bifrost T7.1 — Skill Bridge Compatibility Documentation. Updated for v0.2.1.
