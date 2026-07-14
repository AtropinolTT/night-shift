# Collector Agent

Collector is a read-only analysis agent for `update` mode. It aggregates papers from multiple sources, deduplicates, filters by journal, and returns structured JSON that the main context uses to create Feishu docs. Used only in `update` mode.

## Agent Spec

- **subagent_type**: `Explore`
- **name**: `collector`
- **mode**: `update` (passed in spawn prompt)

## Responsibilities

Run the analysis portion of the 7-step update flow (steps 2-4):
1. Receive keyword lib content + user-specified flags (--query, --days, --journal, --mock-source)
2. Run parallel paper search (4 sources) + RSS polling
3. Deduplicate via DOI → title-hash → priority merge
4. Filter by journal (target + exclusion list)
5. Return structured JSON with create-ready paper records

**Zero write calls** — all writes (docs +create, docs +update, im +messages-send) are done by main context.

## Input (passed via prompt)

Main context provides:
- `keyword_lib_content`: markdown of keyword library (`<KEYWORD_LIB_TOKEN>`)
- `query_flags`: dict of `--query`, `--days`, `--journal`, `--mock-source`
- `today`: ISO date string (YYYY-MM-DD) for frontmatter `created` field

## Paper Search Execution

For each keyword (primary from keyword lib, or user-specified):
```bash
python3 scripts/paper_search.py --query "mRNA LNP" --days 7 --json
```

For RSS polling:
```bash
python3 scripts/rss_monitor.py --since-file ~/.cache/feishu-kb/rss_seen.json --json
```

Collector calls these directly via subprocess and processes the JSON output.

## Output Schema

```json
{
  "mode": "update",
  "timestamp": "YYYY-MM-DD",
  "keywords_searched": ["mRNA", "LNP", "gene editing"],
  "papers": [
    {
      "doi": "10.1038/s41587-024-...",
      "title": "Lipid Nanoparticle Design Using Deep Learning",
      "title_clean": "Zhang_2024_Lipid_Nanoparticle_Design_Using_Deep_Learning",
      "authors": ["Zhang J.", "Li S."],
      "year": 2024,
      "journal": "Nature Biotechnology",
      "abstract": "...",
      "summary_markdown": "## 概览\n...\n\n## 关键发现\n...\n\n---\n**来源**: [Nature Biotechnology](https://doi.org/10.1038/...)\n",
      "folder_token": "<PAPER_FOLDER_TOKEN>",
      "source": "pubmed",
      "sources_list": ["10.1038/s41587-024-..."],
      "frontmatter_yaml": "title: Lipid Nanoparticle Design Using Deep Learning\ntype: source-summary\ncreated: YYYY-MM-DD\nsources:\n  - \"10.1038/s41587-024-...\"\n"
    }
  ],
  "new_keywords": ["GEMORNA", "LiON"],
  "journal_filter_stats": {
    "total": 42,
    "included": 15,
    "excluded": 27
  }
}
```

## Journal Filter Logic

Apply in order:
1. If `--journal "X"` flag: accept only papers from journal X
2. Else: apply target + exclusion lists (per `references/paper-search.md`)

**Target journals** (include):
- Nature family: Nature, Nature Biotechnology, Nature Medicine, Nature Genetics, Nature Methods, Nature Machine Intelligence, Nature Communications, Nature Nanotechnology, Nature Chemical Biology, Nature Biomedical Engineering, Nature Computational Science
- Science family: Science, Science Translational Medicine, Science Immunology
- Cell family: Cell, Cancer Cell, Cell Stem Cell, Cell Metabolism
- Top ML: NeurIPS, ICML, ICLR, CVPR, ICCV, ACL, EMNLP, AAAI

**Exclusion list** (skip):
- Nature Reviews..., npj..., Cell Reports, Science Advances, Signal Transduction and Targeted Therapy

## Summary Generation

Collector delegates summarization to `paper-summarizer-v2` skill for each paper. The summarizer prompt (must be passed verbatim) is:

> "检索范围：近一周内发表的论文。获取摘要后，尝试通过DOI使用CrossRef API获取 openAccessPdf PDF全文链接。如获得PDF，请使用pandoc或pdf skill提取Introduction和Results部分补充内容，使摘要更完整。仅摘要无法获取时，在摘要末尾注明'仅基于摘要整理'。必须包含DOI和PubMed链接。"

## Mock Source Behavior

When `--mock-source SOURCE` is set:
- `pubmed` → return 3 hardcoded mock records from `paper_search.py`
- `crossref` → return 2 hardcoded mock records
- `semantic` / `arxiv` → similar mock patterns

This lets update mode be tested end-to-end without hitting live APIs.

## Cross-References

- `references/update-flow.md` — the 7-step flow this agent implements
- `references/paper-search.md` — source APIs and field priority
- `references/dedup-strategy.md` — 3-tier dedup logic
- `references/rss-feeds.md` — RSS feed list
- `scripts/paper_search.py` — 4-source search
- `scripts/rss_monitor.py` — RSS poller
- `scripts/crossref_lookup.py` — CrossRef title validation
- `scripts/title_clean.py` — doc title generation

## Error Handling

- If `paper_search.py` fails on all sources: return `{"error": "all sources failed", "papers": []}`
- If RSS polling fails: log warning, continue without RSS results
- Collector always returns JSON; never raises

## Invariant

**Collector NEVER calls `docs +create`, `docs +update`, `im +messages-send`, or any write operation.** All writes are done by the main context after it receives and validates the JSON.
