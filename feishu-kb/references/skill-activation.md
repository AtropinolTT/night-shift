# Skill Activation — Trigger Table & Routing Precedence

This file is the **single source of truth for how user input maps to a mode**. The main context consults this on every entry to determine whether the user is asking for `qa` / `maintain` / `update` / help / nothing.

## Modes

| Mode | Subcommand | Purpose | Karpathy mapping |
|------|------------|---------|------------------|
| `qa` | `qa` / `q` / `查询` | Read the KB, answer a question, follow citations, parse PDFs as needed | `query` |
| `maintain` | `maintain` / `m` / `维护` | Lint, dedup, backfill frontmatter, scaffold KG table, append to KB log, IM report | `lint` |
| `update` | `update` / `u` / `检索` | Search 4 sources + RSS, dedup, summarize, create paper docs, append keyword lib, IM report | `ingest` |

`/feishu-kb` was the old name; the new prefix is `feishu-kb`. Both are accepted.

## Trigger Table

The main context tries rules **in this order**. First match wins.

| Priority | Pattern | Mode | Notes |
|----------|---------|------|-------|
| 1 | `feishu-kb help` / `feishu-kb --help` / `feishu-kb -h` | (help) | Print trigger table; do nothing else |
| 2 | `feishu-kb 维护` / `feishu-kb maintain` / `feishu-kb m` / `feishu-kb 维护 --dry-run` | `maintain` | `--dry-run` runs subagents but skips all writes |
| 3 | `feishu-kb 检索` / `feishu-kb update` / `feishu-kb u` / `feishu-kb 检索 --query "..." --days 7` | `update` | Optional flags: `--query`, `--days`, `--journal` (single-name filter), `--mock-source` (test) |
| 4 | `feishu-kb qa <question>` / `feishu-kb q <question>` / `feishu-kb <anything else>` | `qa` | Default — most queries land here |
| 5 | `/loop-weekly-knowledge-base` | `maintain` | Old alias — preserve for backwards compat |
| 6 | `/loop-weekly-paper-search` / `weekly paper search` / `本周文献检索` | `update` | Old aliases from deleted `feishu-kb-update` skill — preserve |

**Bare `feishu-kb` with no argument**: main context runs self-check first, then presents an `AskUserQuestion` with three options:
- **查询知识库** (qa, default) — ask questions, follow citations, parse PDFs
- **维护知识库** (maintain) — dedup, lint, frontmatter backfill, KG scaffold, IM report
- **检索新论文** (update) — search 4 sources + RSS, dedup, create paper docs

If user closes without selecting, defaults to `qa`. If user types a question after the prompt, route to `qa`.

**Bare `feishu-kb` with an unrecognized argument** defaults to `qa` (rule 4). Example: `feishu-kb mRNA` → `qa` mode, query "mRNA".

## Routing Precedence — Why This Order

1. **Explicit help first** — user asking for help should never accidentally trigger a write.
2. **Explicit subcommand before alias** — `feishu-kb 维护` is more reliable than just hoping the user means `qa`.
3. **Chinese alias matches subcommand** — `维护` = `maintain`, `检索` = `update`, `查询` = `qa`. The Chinese word `检索` (search-and-fetch) is unambiguous for the weekly paper search; using it for `qa` would be confusing.
4. **Old aliases last** — `/loop-weekly-*` is from the pre-integration era. We honor them so user muscle memory still works, but they should be the lowest-priority rule.

## Mode-Specific Flags

### `maintain`
- `--dry-run` — subagents run their analysis, but main context prints results instead of executing any `docs +create` / `docs +update` / `im +messages-send`. Use this for the first time after editing the skill, to verify what would change.

### `update`
- `--query "<text>"` — search topic (otherwise uses full keyword library).
- `--days N` — look back N days (default 7).
- `--journal "<name>"` — single-journal filter (e.g., `"Nature Biotechnology"`).
- `--mock-source <name>` — for testing, use only one source (`pubmed` / `crossref` / `semantic` / `arxiv` / `rss`).

### `qa`
- No flags. Q&A is conversational; multi-turn context is held in main-context memory, not passed as flags.

## Multi-Turn (qa only)

In `qa` mode, the main context maintains a small session-local state:

- `last_query`: last user question.
- `last_entities`: entities mentioned in the last answer.
- `last_concepts`: concepts mentioned in the last answer.
- `last_doc_tokens`: doc tokens the librarian fetched this session.

Pronoun resolution ("它", "那", "this paper") maps against `last_entities` / `last_concepts` / `last_doc_tokens` before the librarian is spawned. This is main-context logic, not the librarian's.

## Comparison Detection (qa → maintain side effect)

If the user's question contains a comparison pattern like "X 和 Y 的区别" / "X vs Y vs Z" / "比较 X Y Z" and ≥2 of {X, Y, Z} resolve to existing `entity` docs, the main context prompts:

> "检测到对比问题: X vs Y vs Z. 是否创建/更新 comparison 文档? (y/n)"

On `y`, switch to `maintain` mode (read-only analysis, then user confirms create). On `n`, answer in-line without creating a doc. **Never auto-create** — see `wiki-schema.md` "Comparisons" section.

## Empty / Invalid Input

- Empty input: present mode selection via `AskUserQuestion` (see above).
- Input that does not start with `feishu-kb`, `/loop-weekly-*`, or contain the literal "飞书知识库": **do not trigger**. The skill is a prefix-based or semantic skill, not ambient. (Ambient triggers like "本周文献检索" are handled by rule 6.)

## See Also

- SKILL.md §4 (Trigger Table — summary) and §6 (Shared Rules)
- `write-permissions.md` — what each mode is allowed to write
- `search-scope.md` — folder tokens for KB scope enforcement
