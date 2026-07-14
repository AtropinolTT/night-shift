# CrossRef Helper — DOI → Metadata

Single source for CrossRef API usage. All three modes (qa, maintain, update) use these workflows to validate titles, fetch abstracts, and find PDF links.

## Why CrossRef

CrossRef is the canonical metadata source for academic papers. It has near-complete coverage of DOI-registered papers (Nature, Science, Cell, IEEE, etc.) and exposes a polite REST API. We use it for:

- Title validation before creating a `source-summary` doc (update mode)
- Abstract fetching for PDF-parse confidence comparison (qa mode)
- PDF link retrieval for `drive +upload` to PDFs folder (qa mode)
- Title-only search fallback when DOI is missing (collector, stage 3)

## User-Agent (REQUIRED)

CrossRef's polite pool requires a descriptive User-Agent. Without it, requests may be rate-limited or blocked.

```bash
curl -s -A "Librarian/1.0 (mailto:tangjunjie@chuaibiolab.com)" \
  "https://api.crossref.org/works/{DOI}" \
  -H "Accept: application/json"
```

Replace the email with the user's actual contact (or a generic `noreply@<domain>`). `crossref_lookup.py` (stage 2) sets this automatically.

## DOI Lookup (primary)

```bash
curl -s -A "Librarian/1.0 (mailto:<user-email>)" \
  "https://api.crossref.org/works/{DOI}"
```

Returns JSON with this shape (only the fields we use):

```json
{
  "message": {
    "DOI": "10.1038/s41587-022-01648-0",
    "title": ["Title with <jats:p> markup</jats:p>"],
    "author": [{"given": "J.", "family": "Zhang", ...}, ...],
    "published": {"date-parts": [[2024, 3, 15]]},
    "abstract": "<jats:p>Abstract text...</jats:p>",
    "link": [
      {"URL": "https://...", "content-type": "text/html"},
      {"URL": "https://www.nature.com/articles/foo.pdf", "content-type": "application/pdf"}
    ]
  }
}
```

## Title Extraction

The `title[0]` field often contains `<jats:p>` HTML markup. Strip it:

```python
import re
def clean_text(s: str) -> str:
    s = re.sub(r'<[^>]+>', '', s)        # strip all tags
    s = re.sub(r'\s+', ' ', s).strip()    # collapse whitespace
    return s

title = clean_text(message["title"][0])
```

## Author + Year Extraction

```python
first_author_family = message["author"][0]["family"]   # e.g., "Zhang"
year = message["published"]["date-parts"][0][0]        # e.g., 2024
```

Then assemble the canonical filename (see `title-format.md`):

```
{FirstAuthor}_{Year}_{CleanedFullTitle}
→ Zhang_2024_RNA_Design_Transformer
```

## Abstract Cleaning

`message.abstract` is similar to `title` — strip tags, normalize whitespace.

```python
def clean_abstract(raw: str) -> str:
    raw = re.sub(r'<jats:p>', '', raw)
    raw = re.sub(r'</jats:p>', '\n\n', raw)
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = re.sub(r'&[a-z]+;', ' ', raw)
    return re.sub(r'\s+', ' ', raw).strip()
```

## PDF Link Extraction

```python
def get_pdf_url(message: dict) -> str | None:
    for link in message.get("link", []):
        if link.get("content-type") == "application/pdf":
            return link["URL"]
    return None
```

If `link` has no PDF, fall back to publisher-direct URL patterns:

| Publisher | URL pattern |
|-----------|-------------|
| Nature | `https://www.nature.com/articles/{doi}.pdf` |
| Science | `https://www.science.org/doi/pdf/{doi}` |
| Cell | `https://www.cell.com/cell/doi/pdf/{doi}` |
| bioRxiv | `https://www.biorxiv.org/content/{doi}v1.full.pdf` |

Note: bioRxiv DOIs in CrossRef are preprints. The published version may have a different DOI.

## Title-Only Fallback (no DOI)

When DOI is missing (e.g., an arXiv preprint or an unindexed venue), search by title:

```bash
curl -s -A "Librarian/1.0 (mailto:<user-email>)" \
  "https://api.crossref.org/works?query.title={URL-encoded title}&rows=1"
```

Returns a list of candidates. Match the closest by title similarity (Levenshtein or just substring match after `clean_text()`). If no good match, return `None` — do not fabricate.

## Rate Limits

CrossRef polite pool: **50 requests/second** with descriptive User-Agent. We use single-threaded curl with no burst, so this is never a concern. If a 429 is hit, sleep 5s and retry once.

## What CrossRef Does NOT Have

- Full-text (only abstract). Use the PDF link for full text.
- Citation count or influence metrics. Use Semantic Scholar for that (stage 3).
- Preprint-specific metadata. For arXiv preprints, query arXiv directly.

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| 404 | DOI not registered or typo | Re-check DOI from source; try title fallback |
| 429 | Rate-limited | Sleep 5s, retry once; consider adding API key (not required) |
| Empty `title[0]` | Some book chapters / proceedings have unusual metadata | Try title fallback |
| HTML in title / abstract | JATS markup | Use `clean_text()` / `clean_abstract()` |

## See Also

- `search-scope.md` — PDF folder for downloaded papers
- `title-format.md` — paper title → filename rules
- `paper-search.md` (stage 3) — 4-source API for paper search
