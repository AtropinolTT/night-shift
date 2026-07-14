# QA Mode Tests

These tests cover stage 1 of the integration. Each case is a `feishu-kb` invocation followed by expected behavior. Run all 6 before moving to stage 2 (maintain).

## Test 1 — Basic single-doc lookup

**Input**:
```
feishu-kb GEMORNA 是什么
```

**Expected**:
- Mode detected: `qa` (rule 4, default)
- Librarian spawns and searches 4 folders; finds `实体_GEMORNA` in `<ENTITY_FOLDER_TOKEN>`
- Fetches the doc with `docs +fetch --doc <token>`
- Returns the doc's markdown in the answer
- Cites source: `[实体_GEMORNA](https://your-workspace.feishu.cn/docx/<DOC_TOKEN>)`

**Pass criteria**:
- [ ] Answer contains GEMORNA-specific content (not a generic "mRNA 设计" answer)
- [ ] Source link present and points to `实体_GEMORNA` (not a different doc)
- [ ] No lark-cli write calls in transcript

## Test 2 — Multi-doc synthesis

**Input**:
```
feishu-kb mRNA 序列设计最新进展
```

**Expected**:
- Mode detected: `qa`
- Librarian searches 4 folders for "mRNA 序列设计"
- Finds `概念_mRNA序列设计` (常驻缓存 token `<CACHE_MRNA_TOKEN>`) and any related `论文_*` / `实体_*` docs
- Fetches the cached concept doc first; follows `[[entity-name]]` references in its body (e.g., `[[GEMORNA]]`, `[[LinearDesign]]`, `[[CodonTransformer]]`)
- Synthesizes multi-doc answer; cites all sources

**Pass criteria**:
- [ ] ≥2 distinct doc tokens fetched
- [ ] Answer covers ≥2 entities/methods (e.g., "GEMORNA ... LinearDesign ...")
- [ ] Each cited source has a separate `[name](feishu://...)` link
- [ ] No lark-cli write calls in transcript

## Test 3 — Multi-turn pronoun resolution

**Input** (two turns):
```
feishu-kb GEMORNA 是什么
feishu-kb 它和 mRNABERT 有什么区别
```

**Expected**:
- Turn 1: as Test 1
- Turn 2: main context resolves "它" → `GEMORNA` from session state; spawns librarian with query "GEMORNA 和 mRNABERT 的区别"
- Librarian finds both entity docs; possibly a comparison doc (or detects none exists)

**Pass criteria**:
- [ ] Turn 2 answer references both GEMORNA and mRNABERT specifically
- [ ] If main context detects "X vs Y" pattern, it prompts "create comparison? y/n" (do not auto-create)
- [ ] No lark-cli write calls in transcript (no auto-create)

## Test 4 — Loop detection

**Input**:
```
feishu-kb 概念_基因编辑递送
```

This doc is in the常驻缓存 (`<CACHE_GENE_EDIT_TOKEN>`) and references `概念_LNP设计` and `概念_mRNA序列设计`, which in turn reference each other and back.

**Expected**:
- Librarian fetches `概念_基因编辑递送` (depth 0)
- Follows `[[概念_LNP设计]]` (depth 1)
- Follows `[[概念_mRNA序列设计]]` (depth 2)
- `[[概念_LNP设计]]` again — cycle detected, skip
- `[[概念_基因编辑递送]]` again (transitively) — cycle detected, skip
- Returns within `MAX_DEPTH = 5`

**Pass criteria**:
- [ ] Each doc appears at most once in the `references` tree
- [ ] No infinite recursion / hang
- [ ] Final answer has all 3 concept docs cited

## Test 5 — Forbidden-command guard

**Setup**: read all `*.md` and `*.py` files in `~/.claude/skills/feishu-kb/`. Then run a simple `feishu-kb GEMORNA` query and check the transcript.

**Pass criteria** (all must hold):
- [ ] No `npx @larksuite/cli docs +search` anywhere in source
- [ ] No `npx @larksuite/cli drive +search` anywhere in source
- [ ] No `mcp__pubmed__*`, `mcp__arxiv__*`, or `mcp__chrome_devtools__*` in source
- [ ] No `lark-cli drive +export --file-extension pdf` for paper PDFs
- [ ] Transcript grep for `docs +search|drive +search|mcp__(pubmed|arxiv|chrome)|drive \+export.*pdf` returns nothing

```bash
grep -rE 'docs \+search|drive \+search|mcp__(pubmed|arxiv|chrome)|drive \+export.*pdf' \
  <SKILL_DIR>/ \
  --include='*.md' --include='*.py' \
  | grep -v '^.*#' || echo "OK: no forbidden commands"
```

## Test 6 — Token staleness self-check

**Setup**: temporarily edit `references/search-scope.md` and change the root token `<LIT_ROOT_TOKEN>` to a clearly invalid value like `STALE_TOKEN_TEST_12345`. Then run any qa query.

**Expected**:
- Self-check at mode entry (`drive files list` on root) returns `code != 0` or empty `data.files`
- Main context halts with: `"KB root token stale. Update references/search-scope.md or restore the token. See search-scope.md §Self-Check."`
- No doc fetches or writes attempted

**Pass criteria**:
- [ ] Halt message contains the phrase "search-scope.md"
- [ ] `lark-cli docs +fetch` is NOT called after the failed self-check
- [ ] No lark-cli write calls

**Cleanup**: restore the original token after this test.

## Running the Tests

```bash
# Run each test in a fresh claude --print session
for prompt in \
  "feishu-kb GEMORNA 是什么" \
  "feishu-kb mRNA 序列设计最新进展" \
  ; do
  echo "=== Testing: $prompt ==="
  echo "$prompt" | claude --print 2>&1 | tee /tmp/feishu-kb-qa-test.log
done
```

For multi-turn tests (3, 4), pass each turn as a separate `claude --print` call (since `claude --print` is one-shot, the multi-turn state must be re-established). Or use an interactive session.

## Pass / Fail Recording

Copy this checklist into a test run log:

```
Test 1 (basic lookup):           PASS/FAIL — <notes>
Test 2 (multi-doc synthesis):    PASS/FAIL — <notes>
Test 3 (multi-turn):             PASS/FAIL — <notes>
Test 4 (loop detection):         PASS/FAIL — <notes>
Test 5 (forbidden commands):     PASS/FAIL — <notes>
Test 6 (token staleness):        PASS/FAIL — <notes>
```

If any test fails, do NOT proceed to stage 2. Fix the regression and re-run.
