#!/usr/bin/env python3
"""
title_clean.py — Feishu doc title cleaning and filename generation.

Cleans a raw paper title to the {FirstAuthor}_{Year}_{CleanedTitle}} format
used for source-summary doc names in the 论文 folder.

Usage:
    python title_clean.py "Zhang, J. 2024 Lipid Nanoparticle Design Using Deep Learning"
    python title_clean.py --doi 10.1038/s41587-022-01648-0   # fetch from CrossRef
"""

import re
import sys
import json
import argparse
from typing import Optional

CROSSREF_UA = "Librarian/1.0 (mailto:tangjunjie@chuaibiolab.com)"
CROSSREF_API = "https://api.crossref.org/works"


GREEK = {
    'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta',
    'ε': 'epsilon', 'μ': 'mu', 'π': 'pi', 'σ': 'sigma',
    'Ω': 'omega', 'λ': 'lambda', 'η': 'eta', 'τ': 'tau',
}


def clean_text(s: str) -> str:
    """Strip HTML/JATS tags and collapse whitespace."""
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def clean_title(title: str) -> str:
    """
    Apply cleaning rules to a raw paper title.

    1. Strip HTML/JATS tags
    2. Expand Greek letters
    3. Strip forbidden chars: : , ? ! * / \\ ' " < > ( ) [ ]
    4. Spaces → underscores
    5. Collapse __ → _
    6. Trim leading/trailing _
    7. Truncate to 200 chars at word boundary
    """
    title = clean_text(title)

    # Greek expansion
    for g, exp in GREEK.items():
        title = title.replace(g, exp)

    # Strip forbidden characters
    title = re.sub(r'[:,\?!\*\\/\'\"<>\(\)\[\]]', '', title)

    # Spaces → underscores
    title = '_'.join(title.split())

    # Collapse __
    while '__' in title:
        title = title.replace('__', '_')

    # Trim
    title = title.strip('_')

    # Truncate at word boundary (prefer first 3 + last word if too long)
    if len(title) > 200:
        words = title.split('_')
        if len(words) > 6:
            title = '_'.join(words[:3]) + '_…_' + words[-1]
        else:
            title = title[:200]

    return title


def make_doc_title(first_author: str, year: int, full_title: str) -> str:
    """
    Assemble the canonical Feishu doc title: {FirstAuthor}_{Year}_{CleanedTitle}.
    """
    author = first_author or "Unknown"
    year_str = str(year) if year else "XXXX"
    cleaned = clean_title(full_title)
    return f"{author}_{year_str}_{cleaned}"


def lookup_by_doi(doi: str) -> Optional[dict]:
    """Fetch metadata from CrossRef by DOI."""
    import urllib.request
    url = f"{CROSSREF_API}/{doi}"
    req = urllib.request.Request(url, headers={"User-Agent": CROSSREF_UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            msg = data.get("message", {})
            raw_title = msg.get("title", [""])[0]
            authors = msg.get("author", [])
            first_author = authors[0].get("family", "Unknown") if authors else "Unknown"
            date_parts = msg.get("published", {}).get("date-parts", [[]])
            year = date_parts[0][0] if date_parts and date_parts[0] else None
            return {
                "first_author": first_author,
                "year": year,
                "raw_title": raw_title,
                "cleaned_title": clean_title(raw_title),
                "doc_title": make_doc_title(first_author, year, raw_title),
            }
    except Exception as e:
        print(f"CrossRef lookup failed: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean paper title for Feishu doc naming")
    parser.add_argument("--doi", help="DOI to look up via CrossRef")
    parser.add_argument("--first-author", help="First author last name")
    parser.add_argument("--year", type=int, help="Publication year")
    parser.add_argument("title", nargs="?", help="Raw paper title (use with --first-author and --year)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.doi:
        result = lookup_by_doi(args.doi)
        if result:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            sys.exit(1)
    elif args.title and args.first_author and args.year:
        doc_title = make_doc_title(args.first_author, args.year, args.title)
        if args.json:
            print(json.dumps({
                "raw_title": args.title,
                "first_author": args.first_author,
                "year": args.year,
                "cleaned_title": clean_title(args.title),
                "doc_title": doc_title,
            }, ensure_ascii=False, indent=2))
        else:
            print(doc_title)
    else:
        # Default: read from stdin
        if not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
            if args.first_author and args.year:
                print(make_doc_title(args.first_author, args.year, raw))
            else:
                print(clean_title(raw))
        else:
            parser.print_help()
            sys.exit(1)
