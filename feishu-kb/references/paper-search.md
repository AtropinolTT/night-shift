# Paper Search — 4-Source curl Templates

Each source returns normalized records via `scripts/paper_search.py`. The collector agent uses these in step 2 of the update flow.

## Normalized Record Schema

All 4 sources return records conforming to this schema:

```json
{
  "doi": "10.1038/s41587-024-...",
  "pmid": "40234567",
  "arxiv_id": null,
  "title": "Full paper title",
  "authors": ["Zhang J.", "Li S."],
  "year": 2024,
  "journal": "Nature Biotechnology",
  "abstract": "...",
  "source": "pubmed|crossref|semantic|arxiv"
}
```

Fields may be null if the source doesn't provide them. The dedup step (step 3) fills missing fields via priority merge.

## 1. NCBI PubMed (E-utilities)

API docs: https://eutils.ncbi.nlm.nih.gov/docs/

### Step 1: esearch (find PMIDs)

```bash
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi" \
  -d "db=pubmed" \
  -d "term=mRNA+LNP+AND+(Nature[Journal]+OR+Science[Journal]+OR+Cell[Journal])" \
  -d "reldate=7" \
  -d "datetype=pdat" \
  -d "retmax=20" \
  -d "retmode=json" \
  -d "sort=date"
```

Returns: `{esearchresult: {idlist: ["...", "..."]}}`

### Step 2: esummary (fetch metadata)

```bash
curl -s "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi" \
  -d "db=pubmed" \
  -d "id=40234567,40234568" \
  -d "retmode=json"
```

Returns records with `title`, `authors`, `source`, `pubdate`, `journal`.

**Required User-Agent**:NCBI requires email; add `&email=tangjunjie@chuaibiolab.com` to be nice.

**Rate limit**: 3 requests/second. Sleep 350ms between calls.

## 2. CrossRef

API docs: https://api.crossref.org/docs/

### Bibliographic Search

```bash
curl -s -A "Librarian/1.0 (mailto:tangjunjie@chuaibiolab.com)" \
  "https://api.crossref.org/works?query.bibliographic=mRNA+LNP+lipid+nanoparticle&rows=20&filter=from-pub-date:2026-01-01,until-pub-date:2026-06-01" \
  -H "Accept: application/json"
```

Returns list of items with `DOI`, `title`, `author`, `published.date-parts`, `container-title`.

**Rate limit**: 50 req/s (polite pool). Single-threaded curl is fine.

## 3. Semantic Scholar Graph API

API docs: https://api.semanticscholar.org/graph/v1/

### Paper Search

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=mRNA+LNP+lipid+nanoparticle&year=2026&limit=20&fields=title,authors,year,journal,externalIds,abstract,openAccessPdf" \
  -H "Accept: application/json"
```

Returns papers with Semantic Scholar IDs and openAccessPdf URL.

**Rate limit**: 1 req/s. Sleep 1.1s between calls.

**Fields**: request only what you need (`title,authors,year,journal,externalIds,abstract,openAccessPdf`) to minimize payload.

## 4. arXiv

API docs: https://arxiv.org/help/api/

### Search

```bash
curl -s "https://export.arxiv.org/api/query?search_query=all:mRNA+LNP+lipid+nanoparticle&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending" \
  -H "Accept: application/json"
```

Atom feed returned. Parse `<entry>` elements for `title`, `author`, `published`, `summary`.

**Rate limit**: 1 per 3 seconds. Sleep 3.5s between calls.

**arXiv-specific**: DOIs are often missing; use arXiv ID (`arxiv:2301.12345`) as identifier. Convert to DOI via CrossRef title search if needed.

## Field Priority Merge Table

When the same paper is found via multiple sources, fill fields using this priority (earlier = higher priority, fill-missing only, never overwrite):

| Field | Priority |
|-------|----------|
| `doi` | NCBI > CrossRef > Semantic > arXiv |
| `title` | NCBI > CrossRef > Semantic > arXiv |
| `authors` | CrossRef > NCBI > Semantic > arXiv |
| `year` | CrossRef > NCBI > Semantic > arXiv |
| `journal` | CrossRef > NCBI > Semantic |
| `abstract` | CrossRef > NCBI > Semantic > arXiv |
| `openAccessPdf` | Semantic > CrossRef |

This is implemented in `scripts/paper_search.py` and `dedup-strategy.md`.

## Journal Filter Lists

### Target Journals (high-impact, include)

```
Nature, Nature Biotechnology, Nature Medicine, Nature Genetics,
Nature Methods, Nature Machine Intelligence, Nature Communications,
Nature Nanotechnology, Nature Chemical Biology, Nature Biomedical Engineering,
Nature Computational Science,
Science, Science Translational Medicine, Science Immunology,
Cell, Cancer Cell, Cell Stem Cell, Cell Metabolism,
NeurIPS, ICML, ICLR, CVPR, ICCV, ACL, EMNLP, AAAI, ISMB, RECOMB
```

### Exclusion List (false positives, skip)

```
Nature Reviews Molecular Cell Biology, Nature Reviews Cancer,
Nature Reviews Drug Discovery, Nature Reviews Genetics,
Nature Reviews Immunology, Nature Reviews Microbiology,
npj Vaccines, npj Genomic Medicine, npj Digital Medicine,
Cell Reports, Cell Reports Medicine, Cell Reports Biology,
Science Advances, Signal Transduction and Targeted Therapy,
Communications Biology, Communications Chemistry, Developmental Cell, Molecular Cell
```

## Testing with Mock Source

`paper_search.py --mock-source pubmed` returns 3 hardcoded mock records:
```json
[
  {"doi": "10.1038/s41587-024-00001-x", "title": "Mock Paper 1", "source": "pubmed"},
  ...
]
```

This lets you test the dedup + journal filter + summarization pipeline without live APIs.

## See Also

- `scripts/paper_search.py` — executable aggregator with all 4 sources
- `references/dedup-strategy.md` — 3-tier dedup logic
- `references/update-flow.md` — how paper search fits into the 7-step ingest
