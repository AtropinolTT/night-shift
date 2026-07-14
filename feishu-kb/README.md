# feishu-kb

A unified Feishu (Lark) knowledge base skill for Claude Code — three modes in one skill.

## Overview

| Mode | Karpathy | Purpose |
|------|----------|---------|
| `qa` (default) | `query` | Read KB, answer questions, follow citations, parse PDFs |
| `maintain` | `lint` | Dedup, lint, frontmatter backfill, KG scaffold, log + IM report |
| `update` | `ingest` | 4-source + RSS search, dedup, create paper summaries |

## Quick Start

```
1. Install: npm install -g @larksuite/cli
2. Auth:   npx @larksuite/cli auth login
3. Configure tokens in references/search-scope.md (replace <TOKEN> placeholders)
4. Add permissions to ~/.claude/settings.json (see §11 of SKILL.md)
5. Run: feishu-kb <question>       # qa mode
       feishu-kb 维护             # maintain mode
       feishu-kb 检索 --query "..."  # update mode
```

## Project Structure

```
feishu-kb/
├── SKILL.md                  # Main skill (trigger table + mode definitions)
├── agents/
│   ├── librarian.md          # Shared KB search + citation-follow agent
│   ├── maintainer.md         # Maintain mode analysis agent
│   └── collector.md          # Update mode aggregation agent
├── references/
│   ├── search-scope.md       # Token table (⚠️ replace all <TOKEN> placeholders)
│   ├── write-permissions.md  # Per-mode lark-cli whitelist
│   ├── skill-activation.md   # Trigger table + routing
│   ├── maintain-flow.md      # 7-step maintain flow
│   ├── update-flow.md        # 7-step update flow
│   ├── wiki-schema.md        # Doc frontmatter + page templates
│   ├── title-format.md       # Paper doc naming convention
│   ├── crossref-helper.md   # DOI → metadata workflow
│   ├── paper-search.md       # 4-source curl templates
│   ├── dedup-strategy.md    # DOI + title-hash dedup
│   └── rss-feeds.md          # RSS feed list
├── scripts/
│   ├── fetch_doc.py          # KB read + citation-follow
│   ├── parse_pdf.py          # PDF parsing (conda marker env)
│   ├── backfill_frontmatter.py  # One-shot frontmatter backfill
│   ├── crossref_lookup.py    # CrossRef API client
│   ├── title_clean.py        # Paper title → filename
│   ├── paper_search.py       # 4-source aggregator
│   └── rss_monitor.py        # RSS poller
└── tests/
    ├── test_qa_mode.md
    ├── test_maintain_mode.md
    ├── test_update_mode.md
    └── test_integration.md
```

## Token Configuration

Before first use, replace all `<TOKEN>` placeholders in `references/search-scope.md`:

1. Run `npx @larksuite/cli drive files list --format json` to find your folder tokens
2. Create the 4 required folders in Feishu (文献学习/论文/实体/概念)
3. Create the meta docs (KB index, KB log, keyword library)
4. Update all `<..._TOKEN>` values in search-scope.md

## Frontmatter Format

Uses Lark table format (not YAML `---`) because Feishu's markdown parser strips horizontal rules:

```html
<lark-table rows="4" cols="2" header-row="false">
  <lark-tr><lark-td>title</lark-td><lark-td>Doc Title</lark-td></lark-tr>
  <lark-tr><lark-td>type</lark-td><lark-td>entity</lark-td></lark-tr>
  <lark-tr><lark-td>created</lark-td><lark-td>2026-06-01</lark-td></lark-tr>
  <lark-tr><lark-td>sources</lark-td><lark-td>[]</lark-td></lark-tr>
</lark-table>
```

Valid `type` values: `entity`, `concept`, `source-summary`, `comparison`.

## License

MIT
