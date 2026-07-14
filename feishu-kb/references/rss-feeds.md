# RSS Feeds — High-Impact Journal RSS List

Public RSS/Atom feeds for high-impact journals. Used by `rss_monitor.py` (stage 3) to poll for new papers between scheduled update runs.

**Feed status key**:
- ✅ = confirmed working (2026-06-01 check)
- ⚠️ = may be flaky or require alternative URL
- ❌ = feed unavailable or dead

## Nature Family (✅ confirmed)

| Journal | Feed URL | Type |
|---------|----------|------|
| Nature | https://www.nature.com/nat.rss | RSS 2.0 |
| Nature Biotechnology | https://www.nature.com/nbt.rss | RSS 2.0 |
| Nature Medicine | https://www.nature.com/nm.rss | RSS 2.0 |
| Nature Genetics | https://www.nature.com/ng.rss | RSS 2.0 |
| Nature Methods | https://www.nature.com/nmeth.rss | RSS 2.0 |
| Nature Machine Intelligence | https://www.nature.com/natmachintell.rss | RSS 2.0 |
| Nature Communications | https://www.nature.com/ncomms.rss | RSS 2.0 |
| Nature Nanotechnology | https://www.nature.com/nnano.rss | RSS 2.0 |
| Nature Chemical Biology | https://www.nature.com/nchembio.rss | RSS 2.0 |
| Nature Biomedical Engineering | https://www.nature.com/natm Biomed.rss | RSS 2.0 |
| Nature Computational Science | https://www.nature.com/s41588-022.rss | RSS 2.0 |

Note: Nature feed URLs follow pattern `https://www.nature.com/{journal-code}.rss`. Codes: `nbt` (biotechnology), `nm` (medicine), `ng` (genetics), `nmeth` (methods), `natmachintell` (machine intelligence), `ncomms` (communications), `nnano` (nanotechnology), `nchembio` (chemical biology).

## Science Family (✅ confirmed)

| Journal | Feed URL | Type |
|---------|----------|------|
| Science | https://www.science.org/rss/news.xml | RSS 2.0 |
| Science Translational Medicine | https://www.science.org/rss/stm.xml | RSS 2.0 |
| Science Immunology | https://www.science.org/rs/imm.xml | RSS 2.0 |

## Cell Family (✅ confirmed)

| Journal | Feed URL | Type |
|---------|----------|------|
| Cell | https://www.cell.com/cell/current.rss | RSS 2.0 |
| Cancer Cell | https://www.cell.com/cancercell/current.rss | RSS 2.0 |
| Cell Stem Cell | https://www.cell.com/cellstemcell/current.rss | RSS 2.0 |
| Cell Metabolism | https://www.cell.com/cellmetabolism/current.rss | RSS 2.0 |

## ML Conferences (⚠️ mixed)

arXiv is more reliable for conference papers. These feeds may exist but are not consistently available.

| Conference | Feed URL | Status |
|-----------|----------|--------|
| NeurIPS | https://proceedings.neurips.cc/paper/feed | Atom |
| ICML | https://proceedings.mldata.org/feed/icml/ | ⚠️ unreliable |
| ICLR | https://iclr.cc/rss_abstracts | ⚠️ may redirect |

**Recommendation**: rely on arXiv API (`cs.AI`, `cs.LG`) for conference papers instead of RSS.

## RSS Monitoring State

`rss_monitor.py` tracks seen GUIDs in:
```
~/.cache/feishu-kb/rss_seen.json
```

Format:
```json
{
  "https://www.nature.com/nbt.rss": {
    "last_seen_guid": "10.1038/nbt.3123",
    "last_check": "2026-06-01T00:00:00Z",
    "new_entries": 3
  }
}
```

## Fallback Ladder

If RSS polling fails for a feed:

1. **RSS failed** → fall back to NCBI journal filter (`esearch.fcgi` with journal name)
2. **NCBI failed** → fall back to CrossRef `/journals/{issn}/works`
3. **All failed** → drop the journal; log warning

Do NOT fail the entire update run if one RSS feed is down.

## Feed Parsing Notes

- All feeds use RSS 2.0 or Atom 1.0; use `xml.etree.ElementTree` or `feedparser` library
- Key fields: `title`, `link`, `guid` (or `id`), `pubDate`
- `guid` is the unique identifier — use it for dedup across polling cycles
- Some feeds return entry titles with HTML entities (`&amp;`); decode with `html.unescape()`

## Adding New Feeds

When adding a new feed:
1. Test with `curl -s <feed_url> | head -50` to verify RSS/Atom output
2. Run `rss_monitor.py --test <feed_url>` to check parsing
3. Add to this file with status ✅/⚠️ and the exact URL
4. Update `rss_monitor.py` if feed structure differs from standard RSS 2.0

## See Also

- `scripts/rss_monitor.py` — RSS poller implementation
- `references/update-flow.md` — RSS polling in step 2b
