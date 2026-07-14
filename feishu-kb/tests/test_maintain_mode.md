# test_maintain_mode.md — maintain mode test cases

## Test M1: Dry-Run (primary)

**Command**: `feishu-kb 维护 --dry-run`

**Expected behavior**:
1. Self-check passes (`{"ok": true, "files_count": N}`)
2. librarian (mode=maintain) scans KB index + keyword lib
3. maintainer runs lint analysis
4. main context prints full JSON output from maintainer
5. **Zero write calls** — verified via transcript grep:
   ```bash
   grep -E 'docs \+create|docs \+update|im \+messages-send' <transcript>
   # should return nothing
   ```

**Expected JSON keys**: `duplicates`, `lint.warnings`, `lint.errors`, `lint.frontmatter_gaps`, `kg_table`, `log_entry`, `backfill_plan`.

**Pass criteria**: JSON returned with all keys present; no write calls in transcript.

---

## Test M2: Backfill Dry-Run

**Command**: `conda run -n marker python scripts/backfill_frontmatter.py --dry-run`

**Expected behavior**:
1. Walks 4 folders via `drive files list`
2. For each doc: calls `docs +fetch`, runs `parse_frontmatter()`
3. Prints proposed frontmatter for docs missing required fields
4. Prints "All docs already have complete frontmatter" if all complete

**Pass criteria**: No `--mode apply` or write calls; output is human-readable.

---

## Test M3: Backfill Apply (requires live KB)

**Command**: `conda run -n marker python scripts/backfill_frontmatter.py --apply`

**Precondition**: Some docs in KB lack frontmatter (run M2 first to check).

**Expected behavior**:
1. For each doc missing frontmatter: prepend YAML block via `docs +update --mode replace`
2. Idempotent: running again produces same state

**Pass criteria**: `parse_frontmatter()` on each doc returns `complete: true` after apply.

---

## Test M4: Real Maintain Run (requires live KB; skip in CI)

**Command**: `feishu-kb 维护`

**Expected behavior**:
1. Self-check passes
2. Dedup: scan 4 folders, report duplicates
3. Lint: report orphan/stale/frontmatter gaps
4. KG table scaffold (only fills empty)
5. Backfill: apply frontmatter where missing
6. KB log: append entry via `docs +update --mode append`
7. IM: send report to `<IM_USER_ID>`

**Pass criteria**: All 7 steps complete; KB log has new entry; IM sent.

---

## Test M5: Stale Token Self-Check

**Command**: Temporarily replace `<LIT_ROOT_TOKEN>` with `INVALID_TOKEN` in `references/search-scope.md`, then run `feishu-kb 维护 --dry-run`.

**Expected behavior**: Halts immediately with message pointing to `references/search-scope.md`.

**Pass criteria**: Error message contains "search-scope.md" and "stale".

---

## Test M6: Forbidden-Command Guard

**Command**: Run `feishu-kb 维护 --dry-run` and grep all tool calls.

**Expected behavior**: No `lark-cli docs +search`, `lark-cli drive +search`, or `mcp__*` in any transcript.

**Pass criteria**: grep returns empty.
