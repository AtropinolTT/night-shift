# Update Flow — 7-Step Weekly Paper Ingest

Main context + collector agent follow this exact 7-step flow. Reference: `agents/collector.md`, `SKILL.md` §9.

## Step 0: Entry Check

```
feishu-kb 检索 [--query "KEYWORD"] [--days 7] [--journal "Nature"] [--mock-source SOURCE]
```

Flags:
- `--query`: keyword string (required; can be repeated for multiple keywords)
- `--days`: look-back window in days (default: 7)
- `--journal`: limit to a specific journal (optional)
- `--mock-source`: use only one source for testing (pubmed/crossref/semantic/arxiv)

## Step 1: Read Keyword Library + Self-Check

1. `python3 fetch_doc.py --self-check` → must return `{"ok": true, ...}`
2. Fetch keyword library (`<KEYWORD_LIB_TOKEN>`)
3. Extract primary and secondary keywords from keyword lib

Primary keywords (always searched):
- mRNA, LNP, lipid nanoparticle, siRNA, ASO, UTR, codon, CRISPR, gene editing, base editing, prime editing

Secondary keywords (optional, searched less frequently):
- deep learning, transformer, generative AI, mRNA vaccine, ribosome profiling, nanomedicine

If `--query` is provided, it overrides keyword lib (user-specified search).

## Step 2: Parallel Paper Search + RSS Poll

### 2a: Keyword Search (parallel across sources)

For each primary keyword, run `paper_search.py` in parallel:
```bash
python scripts/paper_search.py --query "mRNA LNP" --days 7 --json
```

Sources (stage 3):
| Source | API | Rate limit |
|--------|-----|-----------|
| NCBI PubMed | `esearch.fcgi` + `esummary.fcgi` | 3 req/s |
| CrossRef | `/works?query.bibliographic=` | 50 req/s |
| Semantic Scholar | `/paper/search` | 1 req/s |
| arXiv | `/query?search_query=` | 1 per 3s |

Each source returns normalized records:
```json
{
  "doi": "10.1038/...",
  "pmid": "...",
  "arxiv_id": "...",
  "title": "...",
  "authors": ["Zhang, J.", "Li, S."],
  "year": 2024,
  "journal": "Nature Biotechnology",
  "abstract": "...",
  "source": "pubmed|crossref|semantic|arxiv"
}
```

### 2b: RSS Polling (parallel across feeds)

Run `rss_monitor.py`:
```bash
python scripts/rss_monitor.py --since-file ~/.cache/feishu-kb/rss_seen.json --json
```

Returns new papers from high-impact journal RSS feeds. See `references/rss-feeds.md` for the confirmed-working feed list.

## Step 3: Deduplication

Three-tier dedup (per `dedup-strategy.md`):

1. **DOI exact match** — primary key
2. **Title-hash fallback** — sha256(lowercase + strip non-alnum) first 8 chars
3. **Priority merge** — when same paper found in multiple sources, merge fields (NCBI > CrossRef > Semantic > arXiv, fill-missing only)

Result: a flat list of unique papers with the best available metadata per source.

## Step 4: Journal Filter

Apply target journal list (from keyword lib + `feishu-kb-update.skills.md`):

**Include** (high-impact):
- Nature family: Nature, Nature Biotechnology, Nature Medicine, Nature Genetics, Nature Methods, Nature Machine Intelligence, Nature Communications, Nature Nanotechnology, Nature Chemical Biology, Nature Biomedical Engineering, Nature Computational Science
- Science family: Science, Science Translational Medicine, Science Immunology
- Cell family: Cell, Cancer Cell, Cell Stem Cell, Cell Metabolism
- Top ML: NeurIPS, ICML, ICLR, CVPR, ICCV, ACL, EMNLP, AAAI

**Exclude** (common false positives):
- Nature Reviews..., npj..., Cell Reports, Science Advances, Signal Transduction and Targeted Therapy

If `--journal "X"` flag is provided: only accept papers from journal X.

## Step 5: Paper Summarization (Parallel)

For each filtered paper, spawn a summarizer using `paper-summarizer-v2` skill:

**MUST pass verbatim to the summarizer subagent:**
> "检索范围：近一周内发表的论文。获取摘要后，尝试通过DOI使用CrossRef API获取 openAccessPdf PDF全文链接。如获得PDF，请使用pandoc或pdf skill提取Introduction和Results部分补充内容，使摘要更完整。仅摘要无法获取时，在摘要末尾注明'仅基于摘要整理'。必须包含DOI和PubMed链接。"

The summarizer returns structured markdown summary with:
- Title, authors, journal, year, DOI
- Abstract (from CrossRef or source)
- Key findings
- Methods (if PDF available)
- Limitations
- Relevance to keyword

## Step 6: CrossRef Validate + Create Docs (Parallel)

For each summarized paper:

1. **CrossRef validate title**:
   ```bash
   python scripts/crossref_lookup.py --doi <doi> --json
   ```
   If DOI not found in CrossRef, try title-only fallback:
   ```bash
   python scripts/crossref_lookup.py --title "<raw title>" --json
   ```

2. **Generate doc title**:
   ```bash
   python scripts/title_clean.py --first-author <family> --year <year> "<raw title>"
   ```
   Output: `FirstAuthor_Year_CleanedTitle`

3. **Create Feishu doc**:
   ```bash
   npx @larksuite/cli docs +create \
     --folder-token <PAPER_FOLDER_TOKEN> \
     --title "<FirstAuthor_Year_CleanedTitle>" \
     --markdown "<summary content with YAML frontmatter>"
   ```

4. **Append frontmatter** at top of doc body:
   ```yaml
   ---
   title: <validated title>
   type: source-summary
   created: YYYY-MM-DD
   sources:
     - "<doi>"
   ---
   ```

## Step 7: Update Keyword Library + IM Report

### 7a: Append new keywords
If new model/technique names found in summaries (e.g., GEMORNA, LiON), append to keyword lib:
```bash
npx @larksuite/cli docs +update --doc <KEYWORD_LIB_TOKEN> --markdown "\n- NewTerm" --mode append
```

### 7b: Send IM report
To `<IM_USER_ID>`:
```
本周文献检索完成 (YYYY-MM-DD)
- 搜索关键词: mRNA, LNP, ...
- 发现 N 篇新论文
- 创建 N 篇摘要文档
- 详见 文献学习/论文 folder
```

## Mock Source Mode

For unit testing without hitting live APIs:
```
feishu-kb 检索 --query "mRNA" --mock-source pubmed
```
- `--mock-source pubmed` → returns 3 hardcoded mock records
- `--mock-source crossref` → returns 2 mock records
- Other sources: same pattern

See `tests/test_update_mode.md` for full mock behavior.

## Cross-References

- `agents/collector.md` — collector agent prompt
- `references/paper-search.md` — per-source curl templates
- `references/dedup-strategy.md` — DOI + title-hash + priority merge
- `references/rss-feeds.md` — confirmed-working RSS feed list
- `scripts/paper_search.py` — 4-source aggregator
- `scripts/rss_monitor.py` — RSS poller
- `scripts/crossref_lookup.py` — CrossRef client
- `scripts/title_clean.py` — title cleaning
- `write-permissions.md` § update — allowed write commands
