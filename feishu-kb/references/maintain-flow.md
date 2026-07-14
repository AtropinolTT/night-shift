# Maintain Flow — 7-Step Weekly KB Maintenance

Main context + maintainer agent follow this exact 7-step flow. Reference: `agents/maintainer.md`, `SKILL.md` §8.

## Step 0: Entry Check

```
feishu-kb 维护 [--dry-run]
```

- `--dry-run`: maintainer runs all analysis, main context prints JSON, **zero write calls**
- no flag: full run

## Step 1: Read KB State + Self-Check

1. `python3 fetch_doc.py --self-check` → must return `{"ok": true, ...}`
2. Fetch KB index (`<KB_INDEX_TOKEN>`)
3. Fetch KB log (`<KB_LOG_TOKEN>`)
4. Fetch keyword lib (`<KEYWORD_LIB_TOKEN>`)

If self-check fails: halt with "KB root token stale. Update references/search-scope.md".

## Step 2: Mandatory Dedup — 4-Folder Enumeration

**Every maintain run must do this, even if no other lint runs.**

For each of the 4 folders (文献学习 root, 论文, 实体, 概念):
```bash
npx @larksuite/cli drive files list --params '{"folder_token":"<TOKEN>"}' --format json
```

Check for:
- **Exact duplicate titles** within the same folder → flag as duplicate
- **Cross-folder name collisions** → flag (same paper/entity appearing in multiple folders)

If duplicates found: log them. Do NOT delete — hard-deny on delete in all modes.

## Step 3: Lint — Full Analysis

Spawn maintainer agent (mode=maintain) for deep KB analysis:

```
librarian (mode=maintain) → KB index + keyword lib audit → orphan/stale flags
maintainer → lint: contradictory / orphan / missing / stale / duplicate / frontmatter
```

Maintainer returns JSON:
```json
{
  "duplicates": [{"doc_token": "...", "title": "...", "folder": "...", "reason": "..."}],
  "lint": {
    "warnings": ["概念_X references non-existent 实体_Y"],
    "errors": ["实体_Z has no content"],
    "frontmatter_gaps": [{"doc_token": "...", "title": "...", "missing": ["created"]}]
  },
  "kg_table": "## 知识图谱概览\n| 实体 | 概念 | 关系 |\n|------|------|------|\n",
  "log_entry": "## 维护记录 YYYY-MM-DD\n...",
  "backfill_plan": [{"doc_token": "...", "proposed": {"title": "...", "type": "entity", "created": "YYYY-MM-DD", "sources": []}}]
}
```

### Lint Checklist

| Check | What | Action if found |
|-------|------|-----------------|
| Inconsistent frontmatter | type doesn't match parent folder | Flag in `frontmatter_gaps` |
| Orphan docs | doc referenced by no other doc | Warn in `warnings` |
| Stale index | index entry has no matching doc | Add to `stale_index_entries` |
| Duplicate titles | same name in same folder | Add to `duplicates` |
| Missing required fields | frontmatter incomplete | Add to `frontmatter_gaps` |
| Contradictory info | same fact stated differently across docs | Warn in `warnings` |

## Step 4: KG Table Scaffold

**Only fills empty sections. Never overwrites existing table content.**

Fetch KB index. Scan for existing `## 知识图谱概览` section:
- If section exists and has content: skip scaffold
- If section missing or empty: append a scaffold table

KG table format:
```markdown
## 知识图谱概览 (updated YYYY-MM-DD)

| 实体/论文 | 概念 | 关系/摘要 |
|----------|------|---------|
| 实体_GEMORNA | 概念_mRNA序列设计 | GEMORNA 是 mRNA 设计生成模型 |
| ... | ... | ... |
```

## Step 5: Frontmatter Backfill

Run `backfill_frontmatter.py`:
- `--dry-run`: print proposed frontmatter for each doc, no writes
- `--apply`: write frontmatter to all docs missing it

Script logic:
1. Walk 4 folders via `drive files list`
2. For each doc, `docs +fetch` → check frontmatter via `parse_frontmatter()`
3. If incomplete: propose `{title, type (from folder), created (today), sources: []}`
4. Apply via `docs +update --mode prepend` (prepend frontmatter to existing body)

One-shot script — not run on a schedule. Idempotent: running twice produces same result.

## Step 6: Append KB Log Entry

Append to KB log doc (`<KB_LOG_TOKEN>`):
```bash
npx @larksuite/cli docs +update --doc <KB_LOG_TOKEN> --markdown "<log_entry>" --mode append
```

Log entry format:
```markdown
## 维护记录 YYYY-MM-DD

- 本次维护时间: YYYY-MM-DD HH:MM
- 检测到 N 个重复文档
- 建议修复的 frontmatter 缺失: N
- KG table scaffold: [已更新/无需更新]
- 详细 lint 结果:
  - warnings: N
  - errors: N
```

## Step 7: IM Completion Report

Send to `<IM_USER_ID>`:
```
IM title: 知识库维护完成报告 (YYYY-MM-DD)

本周维护完成:
- 检测到 N 个重复
- 修复 N 个 frontmatter 缺失
- KG table: [状态]
- 详细 lint 报告: [KB index doc link]
```

## Dry-Run Guard

When `--dry-run` is set:
- Maintainer agent runs normally and returns full JSON
- Main context **only prints the JSON** — no `docs +create`, `docs +update`, or `im +messages-send` calls
- This allows testing the lint logic without any KB mutation

## See Also

- `agents/maintainer.md` — lint analysis logic
- `scripts/backfill_frontmatter.py` — frontmatter backfill implementation
- `write-permissions.md` § maintain — allowed write commands
- `search-scope.md` — folder tokens for dedup walk
