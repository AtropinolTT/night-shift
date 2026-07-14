# test_update_mode.md — update mode test cases

## Test U1: Single-Source Mock (primary)

**Command**: `feishu-kb 检索 --query "mRNA LNP" --mock-source pubmed`

**Expected behavior**:
1. Self-check passes
2. collector runs `paper_search.py --mock-source pubmed --json`
3. Returns 3 mock records
4. No live API calls (verified via transcript)
5. No write calls (no `--apply` or create)

**Pass criteria**: JSON output contains 3 papers with `source: "pubmed"`; no write calls.

---

## Test U2: Title-Hash Dedup

**Command**: Feed 2 mock records with same title (different case/punctuation) into dedup logic.

**Setup**:
```json
[
  {"title": "Lipid Nanoparticle Design", "doi": null, "source": "pubmed"},
  {"title": "lipid nanoparticle design", "doi": null, "source": "crossref"}
]
```

**Expected**: dedup collapses to 1 record with merged fields (authors/journal from pubmed).

**Pass criteria**: 1 record after dedup.

---

## Test U3: Priority Merge

**Command**: Feed 2 mock records with same DOI but different fields.

**Setup**:
```json
[
  {"doi": "10.1038/s41587-024-00001-x", "title": "LNP Design", "abstract": null, "source": "pubmed"},
  {"doi": "10.1038/s41587-024-00001-x", "title": "LNP Design Using Deep Learning", "abstract": "We present...", "source": "crossref"}
]
```

**Expected**: Merged record has title from pubmed (higher priority), abstract from crossref (fill missing).

**Pass criteria**: merged.title == "LNP Design"; merged.abstract == "We present..."

---

## Test U4: RSS Idempotent First Run

**Command**: `python scripts/rss_monitor.py --since-file /tmp/empty_rss.json --dry-run --json`

**Setup**: `/tmp/empty_rss.json` = `{}`

**Expected**: Returns all entries from feeds (new entries relative to empty state).

**Pass criteria**: `new_entries` count > 0.

---

## Test U5: RSS Second Run (no new)

**Command**: `python scripts/rss_monitor.py --since-file /tmp/rss_state.json --dry-run --json`

**Setup**: `/tmp/rss_state.json` contains state from U4 (with seen_guids).

**Expected**: `new_entries` count = 0 (all GUIDs already seen).

**Pass criteria**: `new_entries` == 0.

---

## Test U6: CrossRef DOI Lookup

**Command**: `python scripts/crossref_lookup.py --doi 10.1038/s41587-024-00001-x --json`

**Expected**: Returns dict with `doi`, `title`, `clean_title`, `first_author`, `year`, `journal`, `abstract`, `pdf_url`.

**Pass criteria**: All fields present and non-null.

---

## Test U7: Title Clean

**Command**: `python scripts/title_clean.py --first-author Zhang --year 2024 "Lipid Nanoparticle Design Using Deep Learning?" --json`

**Expected**: `"doc_title": "Zhang_2024_Lipid_Nanoparticle_Design_Using_Deep_Learning"`

**Pass criteria**: No special chars, spaces as underscores, within 200 chars.

---

## Test U8: Journal Filter — Inclusion

**Setup**: Paper with `journal: "Nature Biotechnology"`

**Expected**: Passes filter (in target list).

**Pass criteria**: included.

---

## Test U9: Journal Filter — Exclusion

**Setup**: Paper with `journal: "Nature Reviews Molecular Cell Biology"`

**Expected**: Rejected by filter (in exclusion list).

**Pass criteria**: excluded.

---

## Test U10: End-to-End Live (requires live KB; skip in CI)

**Command**: `feishu-kb 检索 --query "mRNA" --days 7 --journal "Nature Biotechnology"`

**Precondition**: Live APIs reachable; at least 1 paper matches.

**Expected behavior**:
1. Self-check passes
2. Paper search across sources
3. Dedup + journal filter
4. For each paper: CrossRef validate → title_clean → docs +create in 论文 folder
5. Update keyword lib if new terms found
6. IM report to `<IM_USER_ID>`

**Pass criteria**: New doc created in `<PAPER_FOLDER_TOKEN>` with correct frontmatter.

---

## Test U11: Forbidden-Command Guard

**Command**: Run `feishu-kb 检索 --mock-source pubmed` and grep all tool calls.

**Expected behavior**: No `lark-cli docs +search`, `lark-cli drive +search`, or `mcp__*` in any transcript.

**Pass criteria**: grep returns empty.
