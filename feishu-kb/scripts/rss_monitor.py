#!/usr/bin/env python3
"""
rss_monitor.py — RSS/Atom feed poller for high-impact journals.

Polls confirmed-working RSS feeds (per references/rss-feeds.md), tracks seen
GUIDs in ~/.cache/feishu-kb/rss_seen.json, and returns new entries.

Usage:
    python rss_monitor.py --since-file ~/.cache/feishu-kb/rss_seen.json --json
    python rss_monitor.py --test https://www.nature.com/nbt.rss --json
    python rss_monitor.py --dry-run --json   # poll but don't update state
"""

import re
import sys
import json
import time
import argparse
import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import html
import os
from typing import Optional
from datetime import datetime, timezone

FEEDS = [
    # Nature family
    "https://www.nature.com/nat.rss",
    "https://www.nature.com/nbt.rss",
    "https://www.nature.com/nm.rss",
    "https://www.nature.com/ng.rss",
    "https://www.nature.com/nmeth.rss",
    "https://www.nature.com/natmachintell.rss",
    "https://www.nature.com/ncomms.rss",
    "https://www.nature.com/nnano.rss",
    "https://www.nature.com/nchembio.rss",
    # Science family
    "https://www.science.org/rss/news.xml",
    "https://www.science.org/rss/stm.xml",
    "https://www.science.org/rs/imm.xml",
    # Cell family
    "https://www.cell.com/cell/current.rss",
    "https://www.cell.com/cancercell/current.rss",
    "https://www.cell.com/cellstemcell/current.rss",
    "https://www.cell.com/cellmetabolism/current.rss",
]

STATE_FILE = os.path.expanduser("~/.cache/feishu-kb/rss_seen.json")


def fetch_feed(url: str) -> dict:
    """
    Fetch and parse a single RSS/Atom feed.

    Returns:
        {
            "url": str,
            "ok": bool,
            "error": str or None,
            "entries": [
                {"title": str, "link": str, "guid": str, "pubDate": str}
            ]
        }
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Librarian/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(raw)
        entries = []

        # Detect RSS vs Atom
        if root.tag == "rss" or root.tag == "RDF":
            # RSS 2.0 or RSS 1.0
            ns = ""
            for item in root.iter("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                guid_el = item.find("guid")
                date_el = item.find("pubDate")
                entries.append({
                    "title": html.unescape(title_el.text.strip()) if title_el is not None and title_el.text else "",
                    "link": link_el.text.strip() if link_el is not None and link_el.text else "",
                    "guid": (guid_el.text.strip() if guid_el is not None and guid_el.text else "") or (link_el.text.strip() if link_el is not None and link_el.text else ""),
                    "pubDate": date_el.text.strip() if date_el is not None and date_el.text else "",
                })
        elif root.tag.endswith("feed") or root.tag == "feed":
            # Atom 1.0
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.iter("entry"):
                title_el = entry.find("title")
                link_el = entry.find("link[@rel='alternate']")
                if link_el is None:
                    link_el = entry.find("link")
                id_el = entry.find("id")
                date_el = entry.find("published")
                if date_el is None:
                    date_el = entry.find("updated")
                entries.append({
                    "title": html.unescape(title_el.text.strip()) if title_el is not None and title_el.text else "",
                    "link": link_el.get("href", "") if link_el is not None else "",
                    "guid": (id_el.text.strip() if id_el is not None and id_el.text else "") or (link_el.get("href", "") if link_el is not None else ""),
                    "pubDate": date_el.text.strip() if date_el is not None and date_el.text else "",
                })

        return {"url": url, "ok": True, "error": None, "entries": entries}
    except Exception as e:
        return {"url": url, "ok": False, "error": str(e), "entries": []}


def load_state() -> dict:
    """Load seen GUIDs state from file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    """Save seen GUIDs state to file."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def monitor_feeds(feeds: list, since_state: dict, dry_run: bool = False) -> tuple[list, dict]:
    """
    Poll all feeds, return new entries and updated state.

    Returns:
        (new_entries, updated_state)
    """
    new_entries = []
    updated_state = dict(since_state)

    for url in feeds:
        feed_result = fetch_feed(url)
        if not feed_result["ok"]:
            # Keep existing state for failed feed
            if url in updated_state:
                updated_state[url] = {
                    **updated_state[url],
                    "last_check": datetime.now(timezone.utc).isoformat(),
                    "error": feed_result["error"],
                }
            continue

        old_seen = set(since_state.get(url, {}).get("seen_guids", []))
        new_guids = []

        for entry in feed_result["entries"]:
            guid = entry["guid"]
            if guid and guid not in old_seen:
                new_entries.append({
                    **entry,
                    "source_feed": url,
                    "source": "rss",
                })
                new_guids.append(guid)

        if not dry_run:
            updated_state[url] = {
                "last_check": datetime.now(timezone.utc).isoformat(),
                "seen_guids": list(old_seen | set(new_guids)),
                "new_entries": len(new_guids),
                "error": None,
            }

    return new_entries, updated_state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSS feed monitor")
    parser.add_argument("--since-file", default=STATE_FILE, help="Path to state file")
    parser.add_argument("--feeds-file", help="File with feed URLs (one per line)")
    parser.add_argument("--dry-run", action="store_true", help="Poll but don't update state")
    parser.add_argument("--test", metavar="URL", help="Test a single feed URL")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    feeds = FEEDS
    if args.feeds_file:
        with open(args.feeds_file) as f:
            feeds = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if args.test:
        result = fetch_feed(args.test)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    since_state = {}
    if os.path.exists(args.since_file) and not args.dry_run:
        with open(args.since_file) as f:
            since_state = json.load(f)

    new_entries, updated_state = monitor_feeds(feeds, since_state, dry_run=args.dry_run)

    if args.json:
        print(json.dumps({
            "new_entries": new_entries,
            "feeds_polled": len(feeds),
            "feeds_with_new": sum(1 for url, state in updated_state.items() if state.get("new_entries", 0) > 0),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"New entries: {len(new_entries)}")
        for e in new_entries:
            print(f"  [{e['source_feed'].split('/')[-1]}] {e['title'][:60]}")

    if not args.dry_run:
        save_state(updated_state)
