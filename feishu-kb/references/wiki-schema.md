# Wiki Schema — Karpathy LLM Wiki Alignment

This file defines the structural conventions for all wiki documents. It is the **single source of truth** for doc structure: page types, naming, frontmatter, and cross-references. All new docs created by `update` mode and all old docs that get backfilled must conform.

## Page Types

Every wiki page has a `type` in its frontmatter. The four types come from Karpathy's LLM Wiki pattern:

| Type | Purpose | Lives in folder | Example |
|------|---------|----------------|---------|
| `concept` | Abstract technique or domain (e.g., mRNA sequence design) | 概念 | `概念_mRNA序列设计.md` |
| `entity` | Concrete model, lab, method, or paper (e.g., GEMORNA, LiON) | 实体 | `实体_GEMORNA.md` |
| `source-summary` | One per ingested paper / source | 论文 | `Zhang_2024_RNA_Design.md` |
| `comparison` | Cross-cutting view across multiple entities | comparisons | `comparison_mRNA_design_tools.md` |

The `type` is also implicit in the parent folder: 实体 → entity, 概念 → concept, 论文 → source-summary, comparisons → comparison. `backfill_frontmatter.py` (stage 2) uses this to default the type when backfilling legacy docs.

## Naming Conventions

### Folders
Folders use the type: 实体, 概念, 论文, comparisons (Karpathy-aligned).

### Filenames
**Kebab-case or underscored-as-saved-in-Feishu** — match Feishu's existing title. Two cases:

- **For `source-summary` (论文 folder)**: `第一作者_年份_论文原标题`. Use `title_clean.py` to apply:
  - Spaces → `_`
  - Strip `: , ? ! * / \ ' " < > ( ) [ ]`
  - Collapse `__`; trim leading/trailing `_`
  - Truncate to 200 chars
  - Example: `Zhang_2024_RNA_Design_Transformer.md`

- **For `concept` / `entity` / `comparison`**: keep Feishu's title verbatim (e.g., `概念_mRNA序列设计.md`, `实体_GEMORNA.md`, `comparison_mRNA_design_tools.md`).

## Frontmatter (YAML, at top of every doc)

Required fields (backfill script auto-fills these for legacy docs):

```yaml
---
title: <human-readable title>            # e.g., "GEMORNA: mRNA 设计生成式模型"
type: concept | entity | source-summary | comparison
created: YYYY-MM-DD                       # ISO date
sources:                                  # list of raw sources / DOIs
  - "10.1038/s41587-022-..."
  - "raw/papers/zhang2024.pdf"
---
```

Optional fields (filled in over time):

```yaml
related:                                  # [[wikilinks]] to other wiki pages
  - "[[实体_GEMORNA]]"
  - "[[概念_mRNA序列设计]]"
updated: YYYY-MM-DD                       # last modified date
confidence: high | medium | low           # for qa mode PDF-parse outputs
tags: [mRNA, LNP, gene-editing]           # free-form, for KB index search
```

`librarian` agent parses frontmatter on every fetch and reports `frontmatter_complete: bool`. `maintainer` agent flags docs with incomplete frontmatter in lint.

## Cross-References (`[[wikilinks]]`)

Use Obsidian-style `[[concept-name]]` or `[[entity-name]]` in doc body to reference other wiki pages. **At write time**, the main context renders these as Feishu doc links via `drive files list` lookup:

```
[[GEMORNA]]  →  [实体_GEMORNA](feishu://docs/<ENTITY_FOLDER_TOKEN>)
```

If the target cannot be found (e.g., a typo or not yet created), fall back to literal `[[GEMORNA]]`. This is the qa mode write-time behavior.

**Read time**: librarian / qa user reads `[[GEMORNA]]` literally; resolution happens only at write.

## Comparisons (`comparisons/` folder)

A `comparison` doc synthesizes ≥2 entities or methods. Two creation paths:

1. **User-triggered** (qa mode): user asks "比较 GEMORNA / LinearDesign / CodonTransformer". Librarian detects the "X vs Y vs Z" pattern in the query, fetches all 3 entity docs, and prompts: "Synthesize a comparison?" On user confirm, main context creates a `comparison` doc in `comparisons/` folder.
2. **Maintainer-suggested** (maintain mode): when lint finds a concept with ≥3 referenced entities, log a suggestion in the KB log entry: "建议创建 comparison: concept-X has 3+ entities". **Never auto-create.**

Comparison doc template:

```yaml
---
title: "<comparison topic>: <entities joined by / >"
type: comparison
created: YYYY-MM-DD
sources:
  - "<doi 1>"
  - "<doi 2>"
related:
  - "[[entity_a]]"
  - "[[entity_b]]"
  - "[[entity_c]]"
tags: [<domain 1>, <domain 2>]
---

## 概览
<one-paragraph summary>

## 实体对比表
| 维度 | 实体 A | 实体 B | 实体 C |
|------|--------|--------|--------|
| ... | ... | ... | ... |

## 演进关系
<chronological or methodological lineage>

## 参考文献
<sources>
```

## File Organization Rules

- One concept per doc. If a doc grows past ~3000 words, split by sub-concept.
- Citations: link to `raw/` source (paper PDF or web article) — never bare URLs.
- Updates: append new sections with `## 增量 (YYYY-MM-DD)` headings; preserve history.

## See Also

- `search-scope.md` — folder tokens (concept lives in 概念, etc.)
- `skill-activation.md` — trigger table (qa detects "X vs Y" → comparison prompt)
- `title-format.md` — paper title cleaning rules
- `write-permissions.md` — who can create / update which type
