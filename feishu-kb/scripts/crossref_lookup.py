#!/usr/bin/env python3
"""
crossref_lookup.py — CrossRef API client for DOI/title lookups.

Provides: lookup_by_doi(), lookup_by_title(), clean_abstract(), get_pdf_url().

Usage:
    python crossref_lookup.py --doi 10.1038/s41587-022-01648-0 --json
    python crossref_lookup.py --title "Lipid Nanoparticle Design Using Deep Learning" --json
"""

import re
import sys
import json
import argparse
import urllib.request
import urllib.parse
from typing import Optional, Dict

CROSSREF_UA = "Librarian/1.0 (mailto:tangjunjie@chuaibiolab.com)"
CROSSREF_API = "https://api.crossref.org/works"


def clean_text(s: str) -> str:
    """Strip HTML/JATS tags and collapse whitespace."""
    if not s:
        return ""
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def clean_abstract(raw: str) -> str:
    """
    Clean JATS-formatted abstract from CrossRef.

    - Remove <jats:p> wrapper tags, replacing with double newlines
    - Strip all remaining tags
    - Decode HTML entities
    - Collapse whitespace
    """
    if not raw:
        return ""
    raw = re.sub(r'<jats:p>', '', raw)
    raw = re.sub(r'</jats:p>', '\n\n', raw)
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = re.sub(r'&[a-z]+;', ' ', raw)
    return re.sub(r'\s+', ' ', raw).strip()


def get_pdf_url(message: dict) -> Optional[str]:
    """
    Extract PDF URL from CrossRef message.link.
    Returns the first link with content-type application/pdf, or None.
    """
    for link in message.get("link", []):
        if link.get("content-type") == "application/pdf":
            return link.get("URL")
    return None


def _do_request(url: str) -> dict:
    """Make a CrossRef API request and return parsed JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": CROSSREF_UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def lookup_by_doi(doi: str) -> Optional[Dict]:
    """
    Fetch paper metadata by DOI.

    Returns dict with keys:
        doi, title, clean_title, authors (list of family names),
        first_author, year, abstract, clean_abstract, pdf_url,
        journal, publisher
    Returns None on failure.
    """
    doi = doi.strip()
    if not doi:
        return None
    url = f"{CROSSREF_API}/{doi}"
    try:
        data = _do_request(url)
        msg = data.get("message", {})

        raw_title = msg.get("title", [""])[0] or ""
        authors = msg.get("author", [])
        first_author = authors[0].get("family", "Unknown") if authors else "Unknown"
        date_parts = msg.get("published", {}).get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else None
        raw_abstract = msg.get("abstract", "")
        journal = msg.get("container-title", [""])[0] or ""
        publisher = msg.get("publisher", "")

        return {
            "doi": doi,
            "title": raw_title,
            "clean_title": clean_text(raw_title),
            "authors": [f"{a.get('given','')} {a.get('family','')}".strip() for a in authors],
            "first_author": first_author,
            "year": year,
            "abstract": raw_abstract,
            "clean_abstract": clean_abstract(raw_abstract),
            "pdf_url": get_pdf_url(msg),
            "journal": journal,
            "publisher": publisher,
            "source": "crossref",
        }
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} for DOI {doi}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"CrossRef error: {e}", file=sys.stderr)
        return None


def lookup_by_title(title: str, max_results: int = 5) -> list:
    """
    Search CrossRef by title (title-only fallback when no DOI).

    Returns a list of candidate dicts (same schema as lookup_by_doi,
    but may lack some fields if not returned). Best match is index 0.
    """
    if not title:
        return []
    encoded = urllib.parse.quote_plus(title[:200])
    url = f"{CROSSREF_API}?query.title={encoded}&rows={max_results}"
    try:
        data = _do_request(url)
        candidates = []
        for item in data.get("message", {}).get("items", []):
            raw_title = item.get("title", [""])[0] or ""
            authors = item.get("author", [])
            first_author = authors[0].get("family", "Unknown") if authors else "Unknown"
            date_parts = item.get("published", {}).get("date-parts", [[]])
            year = date_parts[0][0] if date_parts and date_parts[0] else None
            raw_abstract = item.get("abstract", "")
            candidates.append({
                "doi": item.get("DOI", ""),
                "title": raw_title,
                "clean_title": clean_text(raw_title),
                "authors": [f"{a.get('given','')} {a.get('family','')}".strip() for a in authors],
                "first_author": first_author,
                "year": year,
                "abstract": raw_abstract,
                "clean_abstract": clean_abstract(raw_abstract),
                "pdf_url": get_pdf_url(item),
                "journal": item.get("container-title", [""])[0] or "",
                "publisher": item.get("publisher", ""),
                "source": "crossref",
                "score": item.get("score", 0),
            })
        return candidates
    except Exception as e:
        print(f"CrossRef title search error: {e}", file=sys.stderr)
        return []


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CrossRef DOI/title lookup")
    parser.add_argument("--doi", help="DOI to look up")
    parser.add_argument("--title", help="Title search query (title-only fallback)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.doi:
        result = lookup_by_doi(args.doi)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            sys.exit(1)
    elif args.title:
        results = lookup_by_title(args.title)
        if results:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)
