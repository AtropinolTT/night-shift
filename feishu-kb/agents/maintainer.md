# Maintainer Agent

Maintainer is a read-only analysis agent for `maintain` mode. It does NOT write to KB — it returns structured JSON that the main context uses to drive writes. Used only in `maintain` mode.

## Agent Spec

- **subagent_type**: `Explore`
- **name**: `maintainer`
- **mode**: `maintain` (passed in spawn prompt)

## Responsibilities

Run the lint portion of the 7-step maintain flow:

1. Receive KB index doc content + keyword lib content + 4-folder file list from main context
2. Audit for: orphans, stale index entries, duplicates, frontmatter gaps, contradictory info
3. Generate KG table scaffold (if empty)
4. Generate KB log entry (markdown)
5. Generate backfill plan (list of doc tokens → proposed frontmatter)
6. Return all as JSON — **zero write calls**

## Input (passed via prompt)

Main context provides:
- `kb_index_content`: full markdown of KB index doc (`<KB_INDEX_TOKEN>`)
- `keyword_lib_content`: full markdown of keyword lib (`<KEYWORD_LIB_TOKEN>`)
- `folder_listings`: JSON array of `{folder_token, folder_name, files: [{token, name, type}]}` for all 4 folders
- `today`: ISO date string (YYYY-MM-DD) for log entry

## Lint Logic

### Orphan Detection
A doc is "orphaned" if:
- It exists in a folder (found via `drive files list`)
- No other doc in the KB references it (no `[[doc-name]]` or "详见 文档名" pattern pointing to it)
- Exception: high-profile entities (GEMORNA, LiON) are never orphaned even if unreferenced

### Stale Index Detection
An index entry is stale if:
- The index lists `doc_token` X under label "实体_X" or "概念_X"
- `drive files list` on the relevant folder does NOT return a doc with that token

### Duplicate Detection
Duplicates if same `name` appears twice in the same folder via `drive files list`.

### Frontmatter Gap Detection
For each doc in folder listings, maintainer calls `docs +fetch` (via librarian sub-subagent or direct fetch) and runs `parse_frontmatter()`:
- Incomplete if any of the 4 required fields are missing: `title`, `type`, `created`, `sources`
- Type validation: must be one of `concept` / `entity` / `source-summary` / `comparison`

### Contradiction Detection (warnings)
Scan doc bodies for statements that contradict each other across docs:
- Same entity described with different model names/architectures
- Same technique attributed to different labs
- Use simple keyword overlap + heuristics; do NOT fabricate contradictions

## Output Schema

```json
{
  "mode": "maintain",
  "timestamp": "YYYY-MM-DD",
  "kb_index": {
    "total_entries": 42,
    "orphan_entries": [
      {"doc_token": "...", "title": "...", "folder": "概念", "reason": "unreferenced"}
    ],
    "stale_entries": [
      {"label": "实体_X", "reason": "doc token not found in 实体 folder"}
    ]
  },
  "keyword_lib": {
    "primary_keywords": ["mRNA", "LNP", ...],
    "secondary_keywords": [...],
    "missing_keywords": [],
    "new_terms_found": ["GEMORNA", "LiON"]
  },
  "duplicates": [
    {"doc_token": "...", "title": "...", "folder": "论文", "reason": "duplicate title in folder"}
  ],
  "lint": {
    "warnings": [
      "概念_mRNA序列设计 references 实体_GEMORNA but GEMORNA doc describes a different architecture"
    ],
    "errors": [
      "实体_X has empty body (no content)"
    ],
    "frontmatter_gaps": [
      {"doc_token": "...", "title": "...", "folder": "实体", "missing": ["created", "sources"]}
    ]
  },
  "kg_table": "## 知识图谱概览 (updated YYYY-MM-DD)\n\n| 实体/论文 | 概念 | 关系/摘要 |\n|----------|------|---------|\n",
  "log_entry": "## 维护记录 YYYY-MM-DD\n\n- 检测到 N 个问题...\n",
  "backfill_plan": [
    {
      "doc_token": "...",
      "title": "实体_X",
      "folder": "实体",
      "proposed": {
        "title": "实体_X",
        "type": "entity",
        "created": "YYYY-MM-DD",
        "sources": []
      }
    }
  ]
}
```

## Comparison Suggestion Logic

If lint finds a concept doc that references ≥3 entity docs, add to `comparison_suggestions`:

```json
"comparison_suggestions": [
  {"concept": "概念_mRNA序列设计", "entities": ["实体_GEMORNA", "实体_LiON", "实体_RiboDecode"], "reason": "3+ entities under same concept"}
]
```

**Never auto-create** — these go in the log entry for human review.

## Cross-References

- `references/maintain-flow.md` — the 7-step flow this agent implements
- `references/wiki-schema.md` — frontmatter rules and doc types
- `scripts/backfill_frontmatter.py` — applies the backfill_plan
- `agents/librarian.md` (mode=maintain) — librarian audit pass runs before maintainer

## Error Handling

- If any folder listing fails: return `{"error": "folder listing failed for <folder>", ...}` and abort lint
- If a `docs +fetch` fails during frontmatter check: log as `{"doc_token": "...", "error": "fetch failed"}` in frontmatter_gaps
- Maintainer always returns JSON; never raises

## Invariant

**Maintainer NEVER calls `docs +create`, `docs +update`, `im +messages-send`, or any write operation.** All writes are done by the main context after it receives and validates the JSON.
