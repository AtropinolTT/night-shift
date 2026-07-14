#!/usr/bin/env python3
"""
paper_search.py — 4-source paper search aggregator.

Searches NCBI PubMed, CrossRef, Semantic Scholar, and arXiv in parallel,
normalizes results, and deduplicates via DOI → title-hash → priority merge.

Usage:
    python paper_search.py --query "mRNA LNP" --days 7 --json
    python paper_search.py --query "mRNA" --mock-source pubmed --json
    python paper_search.py --doi 10.1038/s41587-024-00001-x --json
"""

import re
import sys
import json
import time
import hashlib
import argparse
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

CROSSREF_UA = "Librarian/1.0 (mailto:tangjunjie@chuaibiolab.com)"
NCBI_EMAIL = "tangjunjie@chuaibiolab.com"

MOCK_PUBMED = [
    {"doi": "10.1038/s41587-024-00001-x", "pmid": "40234567", "title": "Lipid Nanoparticle Design Using Deep Learning", "authors": ["Zhang J.", "Li S."], "year": 2024, "journal": "Nature Biotechnology", "abstract": "We present a deep learning approach for LNP design.", "source": "pubmed"},
    {"doi": "10.1038/s41587-024-00002-y", "pmid": "40234568", "title": "mRNA Vaccine Platform with Enhanced Stability", "authors": ["Wang L."], "year": 2024, "journal": "Nature Medicine", "abstract": "A novel mRNA vaccine platform.", "source": "pubmed"},
    {"doi": "10.1038/s41587-024-00003-z", "pmid": "40234569", "title": "Codon Optimization Using Reinforcement Learning", "authors": ["Kim S.", "Park J."], "year": 2024, "journal": "Nature Methods", "abstract": "RL-based codon optimization.", "source": "pubmed"},
]

MOCK_CROSSREF = [
    {"doi": "10.1038/s41587-024-00004-a", "title": "Base Editing for mRNA Therapeutics", "authors": ["Chen R."], "year": 2024, "journal": "Nature", "abstract": "Base editing in mRNA contexts.", "source": "crossref"},
    {"doi": "10.1038/s41587-024-00005-b", "title": "LNP Pooled Screening for Muscle Delivery", "authors": ["Liu H."], "year": "2024", "journal": "Nature Biotechnology", "abstract": "Pooled LNP screening approach.", "source": "crossref"},
]


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_doi(doi: str) -> str:
    doi = doi.strip().lower()
    doi = re.sub(r'^https?://doi\.org/', '', doi)
    return doi


def title_hash(title: str) -> str:
    import unicodedata
    t = unicodedata.normalize('NFKD', title.lower())
    t = re.sub(r'[^a-z0-9]', '', t)
    t = re.sub(r'\s+', '', t)
    return hashlib.sha256(t.encode()).hexdigest()[:8]


def priority_merge(records: list) -> dict:
    """
    Merge multiple records of the same paper.
    Priority: NCBI > CrossRef > Semantic > arXiv
    Fill missing only — never overwrite existing non-null values.
    """
    priority_order = ["pubmed", "crossref", "semantic", "arxiv"]
    fields = ["doi", "pmid", "arxiv_id", "title", "authors", "year", "journal", "abstract", "source"]

    # Sort by priority
    sorted_recs = sorted(records, key=lambda r: priority_order.index(r.get("source", "arxiv")))

    result = {}
    for f in fields:
        val = None
        for rec in sorted_recs:
            v = rec.get(f)
            if v is not None and v != "":
                val = v
                break
        result[f] = val

    result["sources"] = [r["source"] for r in records if r.get("source")]
    return result


def search_pubmed(query: str, days: int = 7, retmax: int = 20) -> list:
    """Search NCBI PubMed via E-utilities."""
    date_filter = f"({days}[dp])" if days else ""
    term = f"({query}) AND (Nature[Journal] OR Science[Journal] OR Cell[Journal]) {date_filter}".strip()

    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = urllib.parse.urlencode({
        "db": "pubmed", "term": term, "retmax": retmax,
        "retmode": "json", "sort": "date",
        "email": NCBI_EMAIL
    })

    try:
        req = urllib.request.Request(f"{search_url}?{params}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            search_data = json.loads(resp.read())
        ids = search_data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []

        time.sleep(0.35)  # Rate limit: 3 req/s

        # Fetch summaries
        summary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        id_list = ",".join(ids[:retmax])
        sum_params = urllib.parse.urlencode({"db": "pubmed", "id": id_list, "retmode": "json"})
        req2 = urllib.request.Request(f"{summary_url}?{sum_params}")
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            sum_data = json.loads(resp2.read())

        results = []
        for uid, info in sum_data.get("result", {}).items():
            if uid == "uids":
                continue
            results.append({
                "doi": None,
                "pmid": uid,
                "arxiv_id": None,
                "title": info.get("title", ""),
                "authors": [a.get("name", "") for a in info.get("authors", [])],
                "year": int(info.get("pubdate", "0")[:4]) if info.get("pubdate") else None,
                "journal": info.get("source", ""),
                "abstract": None,
                "source": "pubmed",
            })
        return results
    except Exception as e:
        print(f"PubMed error: {e}", file=sys.stderr)
        return []


def search_crossref(query: str, rows: int = 20) -> list:
    """Search CrossRef via their REST API."""
    encoded = urllib.parse.quote_plus(query[:300])
    url = f"https://api.crossref.org/works?query.bibliographic={encoded}&rows={rows}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": CROSSREF_UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        results = []
        for item in data.get("message", {}).get("items", []):
            raw_title = item.get("title", [""])[0] or ""
            authors = item.get("author", [])
            date_parts = item.get("published", {}).get("date-parts", [[]])
            results.append({
                "doi": item.get("DOI", ""),
                "pmid": None,
                "arxiv_id": None,
                "title": clean_text(raw_title),
                "authors": [f"{a.get('given','')} {a.get('family','')}".strip() for a in authors],
                "year": date_parts[0][0] if date_parts and date_parts[0] else None,
                "journal": item.get("container-title", [""])[0] or "",
                "abstract": item.get("abstract", ""),
                "source": "crossref",
            })
        return results
    except Exception as e:
        print(f"CrossRef error: {e}", file=sys.stderr)
        return []


def search_semantic(query: str, limit: int = 20) -> list:
    """Search Semantic Scholar Graph API."""
    encoded = urllib.parse.quote_plus(query[:200])
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded}&limit={limit}&fields=title,authors,year,journal,externalIds,abstract"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        results = []
        for paper in data.get("data", []):
            ext = paper.get("externalIds", {})
            results.append({
                "doi": ext.get("DOI", ""),
                "pmid": ext.get("PubMed", ""),
                "arxiv_id": ext.get("ArXiv", ""),
                "title": paper.get("title", ""),
                "authors": [a.get("name", "") for a in paper.get("authors", [])],
                "year": paper.get("year"),
                "journal": paper.get("journal", ""),
                "abstract": paper.get("abstract", ""),
                "source": "semantic",
            })
        return results
    except Exception as e:
        print(f"Semantic Scholar error: {e}", file=sys.stderr)
        return []


def search_arxiv(query: str, max_results: int = 20) -> list:
    """Search arXiv via Atom API."""
    encoded = urllib.parse.quote_plus(query[:200])
    url = f"https://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/atom+xml"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_text = resp.read().decode("utf-8")

        results = []
        entries = re.findall(r'<entry>(.*?)</entry>', xml_text, re.DOTALL)
        for entry in entries:
            title_match = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
            summary_match = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
            author_matches = re.findall(r'<author>.*?<name>(.*?)</name>', entry, re.DOTALL)
            published_match = re.search(r'<published>(.*?)</published>', entry)
            id_match = re.search(r'<id>(.*?)</id>', entry)

            if not title_match:
                continue
            title = clean_text(title_match.group(1))
            arxiv_id = ""
            if id_match:
                arxiv_id = id_match.group(1).split("/")[-1]

            results.append({
                "doi": None,
                "pmid": None,
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": author_matches,
                "year": int(published_match.group(1)[:4]) if published_match else None,
                "journal": "arXiv",
                "abstract": clean_text(summary_match.group(1)) if summary_match else "",
                "source": "arxiv",
            })
        return results
    except Exception as e:
        print(f"arXiv error: {e}", file=sys.stderr)
        return []


def dedup(records: list) -> list:
    """Three-tier dedup: DOI exact → title-hash → priority merge."""
    # Tier A: DOI groups
    doi_map = {}
    no_doi = []
    for r in records:
        if r.get("doi"):
            doi_map.setdefault(normalize_doi(r["doi"]), []).append(r)
        else:
            no_doi.append(r)

    merged = []
    for doi_key, recs in doi_map.items():
        merged.append(priority_merge(recs))

    # Tier B: title-hash for no-DOI
    hash_map = {}
    for r in no_doi:
        h = title_hash(r.get("title", ""))
        hash_map.setdefault(h, []).append(r)

    for h, recs in hash_map.items():
        merged.append(priority_merge(recs))

    return merged


def search_all(query: str, days: int = 7) -> list:
    """Parallel search across all 4 sources."""
    sources = [
        ("pubmed", lambda: search_pubmed(query, days)),
        ("crossref", lambda: search_crossref(query)),
        ("semantic", lambda: search_semantic(query)),
        ("arxiv", lambda: search_arxiv(query)),
    ]

    all_records = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fn): name for name, fn in sources}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results = fut.result()
                all_records.extend(results)
            except Exception as e:
                print(f"{name} failed: {e}", file=sys.stderr)

    return dedup(all_records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="4-source paper search + dedup")
    parser.add_argument("--query", help="Search query")
    parser.add_argument("--days", type=int, default=7, help="Days lookback (PubMed)")
    parser.add_argument("--doi", help="Single DOI lookup (CrossRef only)")
    parser.add_argument("--mock-source", choices=["pubmed", "crossref", "semantic", "arxiv"], help="Return mock data from one source")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.doi:
        # Single DOI lookup
        url = f"https://api.crossref.org/works/{args.doi}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": CROSSREF_UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            msg = data.get("message", {})
            raw_title = msg.get("title", [""])[0] or ""
            authors = msg.get("author", [])
            date_parts = msg.get("published", {}).get("date-parts", [[]])
            result = {
                "doi": args.doi,
                "pmid": None,
                "arxiv_id": None,
                "title": clean_text(raw_title),
                "authors": [f"{a.get('given','')} {a.get('family','')}".strip() for a in authors],
                "year": date_parts[0][0] if date_parts and date_parts[0] else None,
                "journal": msg.get("container-title", [""])[0] or "",
                "abstract": msg.get("abstract", ""),
                "source": "crossref",
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"DOI lookup failed: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.mock_source == "pubmed":
        print(json.dumps(MOCK_PUBMED, ensure_ascii=False, indent=2))
    elif args.mock_source == "crossref":
        print(json.dumps(MOCK_CROSSREF, ensure_ascii=False, indent=2))
    elif args.query:
        results = search_all(args.query, args.days)
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for r in results:
                print(f"[{r['source']}] {r.get('year', '?')} {r.get('title', '?')[:60]}")
    else:
        parser.print_help()
        sys.exit(1)
