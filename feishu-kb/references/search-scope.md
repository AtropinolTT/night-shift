# Search Scope — Canonical Token Table

**This file is the single canonical source for all KB folder and document tokens.** Every other file in this skill (SKILL.md, agents/*.md, scripts/*.py, references/*.md) cross-references this file. If a token changes (e.g., user restructures the KB in Feishu), edit this file **only**.

## 4-Folder Scope (mandatory for all agents)

All search and enumeration **must** be limited to the following 4 KB folders. Sub-folder expansion via `drive files list --params '{"folder_token":"<ROOT>"}'`.

| Purpose | Folder | Token |
|---------|--------|-------|
| 文献学习 root (主目录) | root | `<LIT_ROOT_TOKEN>` |
| 论文 (paper summaries) | sub | `<PAPER_FOLDER_TOKEN>` |
| 实体 (entities: models, labs, methods) | sub | `<ENTITY_FOLDER_TOKEN>` |
| 概念 (concepts: techniques, domains) | sub | `<CONCEPT_FOLDER_TOKEN>` |
| comparisons (Karpathy-style cross-cuts) | sub | `TBD_Stage1` ← fill in when user creates the folder |

## Other Key Tokens

| Purpose | Token |
|---------|-------|
| KB index doc (知识图谱概览) | `<KB_INDEX_TOKEN>` |
| KB log doc (append-only action log) | `<KB_LOG_TOKEN>` |
| PDF folder (original paper PDFs) | `<PDF_FOLDER_TOKEN>` |
| Keyword library (高/二级关键词) | `<KEYWORD_LIB_TOKEN>` |
| IM user (report recipient) | `<IM_USER_ID>` |
| 常驻缓存: 概念_mRNA序列设计 | `<CACHE_MRNA_TOKEN>` |
| 常驻缓存: 概念_LNP设计 | `<CACHE_LNP_TOKEN>` |
| 常驻缓存: 概念_基因编辑递送 | `<CACHE_GENE_EDIT_TOKEN>` |

## Search Command Template

Use `drive files list` with `folder_token` to enumerate. **Never** use `lark-cli docs +search` or `lark-cli drive +search` (they search the entire drive, outside the KB scope).

```bash
npx @larksuite/cli drive files list \
  --params '{"folder_token":"<TOKEN>"}' \
  --format json
```

To narrow to direct children only (no recursion), add `"type":"folder"` to the params (or filter client-side with `jq`):

```bash
npx @larksuite/cli drive files list \
  --params '{"folder_token":"<ROOT>","type":"folder"}' \
  --format json | jq '.data.files[].token'
```

## Self-Check Command (call at every mode entry)

Each mode's first step must verify the root token is still valid. If this returns `code != 0` or empty `data.files`, halt with a clear error pointing to this file.

```bash
# Self-check: root token still valid?
npx @larksuite/cli drive files list \
  --params '{"folder_token":"<LIT_ROOT_TOKEN>"}' \
  --format json | jq '.code, (.data.files | length // 0)'
# Expect: 0, ≥1
```

If the check fails:
1. The user may have renamed/moved/deleted a folder in Feishu web UI
2. Update the token in this file
3. Retry the self-check

## Forbidden Commands (NEVER use)

| Command | Why forbidden |
|---------|---------------|
| `lark-cli docs +search` | Searches **entire** Feishu docs, not limited to KB scope |
| `lark-cli drive +search` | Same — searches whole drive |
| `lark-cli drive +export --file-extension pdf` for raw paper PDFs | Produces Feishu docx-to-PDF export, NOT the original paper. Use CrossRef PDF link instead. |
| `mcp__pubmed__*` | Not available in this environment |
| `mcp__arxiv__*` | Not available in this environment |
| `mcp__chrome_devtools__*` | Not available in this environment |
| `WebFetch` / `WebSearch` (Claude Code tools) | Replaced by `curl` with per-domain prefixes for audit clarity |

## Editing This File

When a token changes:
1. Update the table above
2. Run `diff` between this file and any other file that hardcodes the token (run the verification command from the plan file)
3. Re-run the self-check
4. The `tests/test_qa_mode.md` token-staleness scenario (case 6) verifies this path

## See Also

- `write-permissions.md` — per-mode write whitelist
- `wiki-schema.md` — doc structure / frontmatter rules
- `skill-activation.md` — trigger table and routing
