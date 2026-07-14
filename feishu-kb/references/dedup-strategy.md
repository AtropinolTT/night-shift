# Dedup Strategy — 3-Tier Paper Deduplication

Used by the collector agent (stage 3) and `paper_search.py` to collapse multi-source results into a unique paper list.

## Three-Tier Dedup

### Tier A: DOI Exact Match (primary)

If two records have the same DOI (case-insensitive, stripped):
- They refer to the same paper
- Merge fields using priority table (fill missing, never overwrite)

DOI normalization:
```python
doi = doi.strip().lower()
doi = re.sub(r'^https?://doi\.org/', '', doi)  # strip URL prefix
```

### Tier B: Title-Hash Fallback

If no DOI is available (e.g., arXiv preprints, some conference papers):

1. Normalize title: lowercase, strip non-alphanumeric, collapse spaces
2. Compute SHA256, take first 8 hex chars as hash
3. Records with identical title-hash → same paper

```python
import hashlib, re
def title_hash(title: str) -> str:
    t = title.lower()
    t = re.sub(r'[^a-z0-9]', '', t)
    t = re.sub(r'\s+', '', t)
    return hashlib.sha256(t.encode()).hexdigest()[:8]
```

Title normalization examples:
- `"Lipid Nanoparticle Design Using Deep Learning"` → `lipidnanoparticleusingdee...` (64 hex → first 8)
- `"Lipid-nanoparticle design using deep learning"` → same hash (hyphen stripped)
- `"LIPID NANOPARTICLE DESIGN USING DEEP LEARNING"` → same hash (lowercased)

### Tier C: Priority Merge

When the same paper is found via multiple sources, merge fields:

```
Priority (high to low): NCBI > CrossRef > Semantic Scholar > arXiv
```

Fill-missing rule: a field from higher-priority source overwrites `null` in lower-priority source, but never overwrites an existing non-null value.

**Merge algorithm (pseudocode)**:
```python
def merge(a, b):
    # a = higher priority record, b = lower priority
    result = {}
    for field in SHARED_FIELDS:
        val_a = getattr(a, field)
        val_b = getattr(b, field)
        result[field] = val_a if val_a is not None else val_b
    return result
```

## Worked Example

**Record 1** (from NCBI):
```json
{"doi": "10.1038/s41587-024-00001-x", "title": "Lipid Nanoparticle Design",
 "authors": ["Zhang J."], "year": 2024, "journal": "Nature Biotechnology",
 "abstract": null, "source": "pubmed"}
```

**Record 2** (from CrossRef):
```json
{"doi": "10.1038/s41587-024-00001-x", "title": "Lipid Nanoparticle Design Using Deep Learning",
 "authors": ["Zhang J.", "Li S."], "year": 2024,
 "journal": "Nature Biotechnology", "abstract": "We present a...", "source": "crossref"}
```

**Merged result**:
```json
{"doi": "10.1038/s41587-024-00001-x",
 "title": "Lipid Nanoparticle Design",  // NCBI (higher priority, non-null)
 "authors": ["Zhang J.", "Li S."],         // CrossRef fills missing from NCBI
 "year": 2024,
 "journal": "Nature Biotechnology",
 "abstract": "We present a...",              // CrossRef fills null from NCBI
 "source": "pubmed"}
```

Note: title kept from NCBI (higher priority) even though CrossRef has a longer variant.

## Implementation

`paper_search.py` implements all three tiers:

```python
def dedup(records: list[dict]) -> list[dict]:
    # Tier A: group by DOI
    doi_map = {}
    no_doi = []
    for r in records:
        if r.get("doi"):
            doi_map.setdefault(normalize_doi(r["doi"]), []).append(r)
        else:
            no_doi.append(r)

    merged = []
    for doi, recs in doi_map.items():
        merged.append(priority_merge(recs))

    # Tier B: title-hash for no-DOI records
    hash_map = {}
    for r in no_doi:
        h = title_hash(r.get("title", ""))
        hash_map.setdefault(h, []).append(r)
    for h, recs in hash_map.items():
        merged.append(priority_merge(recs))

    return merged
```

## Edge Cases

| Case | Handling |
|------|----------|
| Same DOI, different title | Keep title from higher-priority source |
| No DOI, no title | Drop the record (cannot dedup) |
| arXiv + published version | If arXiv has no DOI but title matches a published DOI record, prefer the published version (has DOI = Tier A match) |
| Title with unicode | Normalize to ASCII before hashing; use `unicodedata.normalize('NFKD', t)` |
| Very short title | Still hashable; no minimum length |

## See Also

- `scripts/paper_search.py` — implementation
- `references/paper-search.md` — field priority table
- `references/update-flow.md` — how dedup fits into step 3
