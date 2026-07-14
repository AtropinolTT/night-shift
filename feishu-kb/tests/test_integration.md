# Integration Tests

These tests span multiple modes. They run **after** each individual mode's tests pass:
- Cross-mode integration runs after stage 1 (qa) and stage 2 (maintain) complete.
- Full qa→update→maintain→qa chain runs after stage 3.

The skeleton below will be filled in as each stage lands.

## Test 7 — qa → update → qa round-trip (REQUIRES STAGE 3)

**Setup**: pick a topic that has at least one existing doc in `概念_*` (e.g., "mRNA LNP").

**Steps**:
1. Run `feishu-kb mRNA LNP 是什么` — qa returns existing `概念_LNP设计` content.
2. Run `feishu-kb 检索 --query "mRNA LNP" --days 7` — update ingests new papers.
3. Run `feishu-kb mRNA LNP 是什么` again — qa should now return the original concept doc **plus** cite the new paper docs from step 2.

**Pass criteria**:
- [ ] Step 3 answer includes paper titles from step 2 as sources
- [ ] All step 2 papers have complete frontmatter (title, type=source-summary, created, sources[doi])
- [ ] No duplicate docs created (dedup works)
- [ ] No orphan docs in KB index (maintainer-relevant, but verified at maintain time)

**Stage status**: BLOCKED until stage 3 ships. Skeleton only.

## Test 8 — update → maintain round-trip (REQUIRES STAGE 2 + 3)

**Setup**: ensure KB is in a known state (e.g., run maintain once to baseline).

**Steps**:
1. Snapshot the KB log: `npx @larksuite/cli docs +fetch --doc <KB_LOG_TOKEN>` → save to `/tmp/kb_log_before.json`.
2. Run `feishu-kb 检索 --query "mRNA" --days 1 --mock-source pubmed` — update creates 0-3 new paper docs.
3. Run `feishu-kb 维护` — maintain runs lint + KG scaffold + log append.
4. Re-snapshot: `... +fetch --doc <KB_LOG_TOKEN>` → save to `/tmp/kb_log_after.json`.
5. Diff the two snapshots.

**Pass criteria**:
- [ ] Log entry from step 3 mentions the new paper(s) from step 2 by title
- [ ] KG table (in `<KB_INDEX_TOKEN>`) has a `updated YYYY-MM-DD` section if any concept gained new related entities
- [ ] Lint reports 0 new frontmatter gaps (papers created in step 2 should have complete frontmatter)
- [ ] No docs deleted or moved

**Stage status**: BLOCKED until stage 2 + 3 ship. Skeleton only.

## Test 9 — qa frontmatter awareness (REQUIRES STAGE 2 + backfill)

**Setup**: after `backfill_frontmatter.py --apply` has run, all legacy docs should have frontmatter.

**Steps**:
1. Run `feishu-kb 概念_mRNA序列设计` — qa fetches the doc.
2. Check the doc body for frontmatter at the top.

**Pass criteria**:
- [ ] First ~10 lines of the doc are valid YAML frontmatter
- [ ] Frontmatter contains `title`, `type: concept`, `created` (date), `sources` (list, may be empty)
- [ ] QA answer correctly identifies doc type and creation date in metadata

**Stage status**: BLOCKED until backfill runs in stage 2. Skeleton only.

## Test 10 — write-permission enforcement (qa isolation)

**Setup**: monitor main context for any `lark-cli docs +create` calls during a pure qa session.

**Steps**:
1. Run a long qa session: `feishu-kb mRNA 序列设计`, follow-up turns.
2. Grep the transcript for `docs +create`.

**Pass criteria**:
- [ ] Zero `docs +create` calls during qa session
- [ ] If user asks qa to "create a new entity", main context responds with the routing hint (see `write-permissions.md` qa section) instead of creating

**Stage status**: ACTIVE in stage 1 — verifiable now.

## Test 11 — pre-permissions allowlist works

**Setup**: ensure `~/.claude/settings.json` has the `permissions.allow` block from SKILL.md §11.

**Steps**:
1. Run any qa query and observe whether Claude Code prompts for permission.
2. Run any `feishu-kb 维护 --dry-run` and observe.

**Pass criteria**:
- [ ] No permission prompts for `npx @larksuite/cli drive files list*`
- [ ] No permission prompts for `npx @larksuite/cli docs +fetch*`
- [ ] No permission prompts for `npx @larksuite/cli docs +create*` (when maintain/update later run)
- [ ] No permission prompts for `curl -s -A *https://api.crossref.org*`

**Stage status**: ACTIVE in stage 1 — verifiable now once user adds the block.

## Running Integration Tests

Each integration test is multi-step and may need staged execution:

```bash
# Capture full transcripts
nohup claude --print > /tmp/feishu-kb-integration.log 2>&1 <<'EOF'
feishu-kb mRNA LNP 是什么
feishu-kb 检索 --query "mRNA LNP" --days 7
feishu-kb mRNA LNP 是什么
feishu-kb 维护
EOF

# Inspect for forbidden patterns
grep -E 'docs \+search|drive \+search' /tmp/feishu-kb-integration.log && echo "FAIL" || echo "OK"
```

## Pass / Fail Recording

```
Test 7  (qa→update→qa):         PASS/FAIL — <notes>   [stage 3]
Test 8  (update→maintain):      PASS/FAIL — <notes>   [stage 2+3]
Test 9  (qa frontmatter):       PASS/FAIL — <notes>   [stage 2]
Test 10 (qa write isolation):   PASS/FAIL — <notes>
Test 11 (pre-permissions):      PASS/FAIL — <notes>
```

## Notes for Future Iterations

- v1.1: add a test that runs `feishu-kb --init` to walk the drive and regenerate `search-scope.md` (planned for v1.1, not v1.0).
- v1.1: add a quantitative test (timing + token usage) to detect regressions.
- v1.1: add a test for `comparisons/` creation (qa detects "X vs Y" pattern → user confirms → maintain creates).
