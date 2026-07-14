# bifrost-fusion-provider-fix - Work Plan

## TL;DR (For humans)
Fix all known bifrost issues in dependency order: (1) revert orphaned config keys, (2) fix stdout pollution corrupting MCP protocol, (3) redesign fusion to use OpenCode's providers via the plugin SDK instead of the companion managing API keys. The companion stops making LLM calls entirely; the plugin handles all model dispatch through `client.session.prompt()`. The companion retains all non-fusion features (memory, classifier, goals, skills).

## Scope
**IN:**
- C3: Remove `deepseek_api_key` / `openai_api_key` from `companion/config.py`
- C1: Identify and fix stdout pollution from the companion process
- C2: Move fusion model calls from Python companion to TypeScript plugin using OpenCode SDK (`client.session.prompt()`)
- C4: Remove dead `_get_opencode_api_keys()` from `dispatch.py` (subsumed by C2)

**OUT:**
- No changes to non-fusion companion features (memory, classifier, goal loop, skills)
- No changes to OpenCode itself
- No new npm publish (already blocked by 2FA)

## Verification strategy
- C3: `python3 -c "from companion.config import DEFAULTS; assert 'deepseek_api_key' not in DEFAULTS"` — exit 0
- C1: `python3 companion/server.py 2>/dev/null | head -1` — first line is valid JSON-RPC
- C2: `/fusion "hello"` in OpenCode returns real model responses (not mock) through OpenCode's configured deepseek provider
- Full: Plugin compiles with `npx tsc --noEmit` — 0 errors

## Execution strategy

### Dependency graph
```
C3 (config revert) ──→ C1 (stdout fix) ──→ C2 (fusion redesign)
                                              └── C4 (dead code removal)
```

C3 is independent and immediate. C1 needs user diagnostic first. C2 is the main work and subsumes C4.

### Wave 1: C3 (config cleanup) + C1 investigation
- Revert config.py API key fields
- User runs stdout diagnostic, reports result
- If stdout pollution found, fix it; if not, document as OpenCode-side issue

### Wave 2: C2 (fusion redesign)
- Plugin uses `client.session.prompt()` for model calls
- Companion fusion_dispatch_tool deprecated
- dispatch.py stripped of API key resolution, mock fallback removed
- Cost tracking, synthesis prompt, and formatting replicated in TypeScript

## Todos

### T1: Revert config.py API key additions
**References**: `bifrost/companion/config.py:23-25` — our earlier edit added `deepseek_api_key: ""` and `openai_api_key: ""`
**Acceptance**: `DEFAULTS` dict no longer contains API key keys
**QA scenario (happy)**: Import passes; no key-related attributes in `DEFAULTS`
**QA scenario (failure)**: Assertion fails if keys remain
**Commit**: `fix(companion): revert API key fields from config.py`

### T2: Diagnose and fix stdout pollution
**References**: `bifrost/companion/server.py` — MCP server uses stdio transport
**Acceptance**: `python3 companion/server.py 2>/dev/null | head -1` outputs valid JSON-RPC
**QA scenario (happy)**: First stdout line matches `^{"jsonrpc":"2.0"` —
**QA scenario (failure)**: Non-JSON output detected; add `sys.stderr` redirection or remove stray print
**Commit**: `fix(companion): redirect stray stdout output to stderr`

### T3: Implement plugin-side model dispatch
**References**: `bifrost/plugin/index.ts:430-525` — `/fusion` handler; `@opencode-ai/sdk` — `client.session.create()`, `.prompt()`, `.messages()`, `.delete()`
**Acceptance**: Plugin creates temp sessions, sends prompts to configured models, collects responses via OpenCode's provider auth
**QA scenario (happy)**: 2 temp sessions created, prompts sent, responses collected
**QA scenario (failure)**: SDK call fails; plugin returns graceful error
**Commit**: `feat(plugin): add SDK-based model dispatch for fusion`

### T4: Implement plugin-side synthesis and cost tracking
**References**: `bifrost/companion/fusion/dispatch.py:45-58` — `SYNTHESIS_PROMPT_TEMPLATE`; `dispatch.py:35-43` — `MODEL_RATES`; `dispatch.py:94-97` — `_estimate_cost()`
**Acceptance**: Plugin runs synthesis via another temp session, calculates wall time + token costs, produces identical `FusionResult` shape
**QA scenario (happy)**: Synthesis prompt matches Python template verbatim; cost output matches format
**QA scenario (failure)**: Synthesis model times out or returns error; partial results returned
**Commit**: `feat(plugin): add synthesis and cost tracking for fusion`

### T5: Deprecate companion fusion dispatch + remove dead code
**References**: `bifrost/companion/fusion/dispatch.py:108-132` — `_get_opencode_api_keys()`; `server.py:24` — `from companion.fusion.dispatch import fusion_dispatch`; `server.py:175-192` — `fusion_dispatch_tool` MCP tool
**Acceptance**: `_get_opencode_api_keys()` removed; `_call_model()` removed; `fusion_dispatch_tool` returns deprecation message; `server.py` import updated
**QA scenario (happy)**: Companion starts without errors; fusion MCP tool returns "deprecated" message
**QA scenario (failure)**: Old code still referenced; import error
**Commit**: `refactor(companion): deprecate fusion dispatch, remove dead API key resolution`

### T6: Rebuild plugin and verify
**References**: `bifrost/plugin/` — TypeScript build
**Acceptance**: `npx tsc --noEmit` — 0 errors
**QA scenario (happy)**: Clean tsc output, exit 0
**QA scenario (failure)**: Type errors; fix and rebuild
**Commit**: `chore(plugin): rebuild after fusion refactor`

## Final verification wave
F1: **Plan compliance audit** — All 6 todos complete, no scope creep
F2: **Code quality review** — No dead code, no API key in companion, no mock fallback
F3: **Real manual QA** — `/fusion "hello"` in OpenCode returns real model responses through configured deepseek provider
F4: **Scope fidelity** — Non-fusion companion features unchanged (memory, classifier, goal loop, skills)

## Commit strategy
- Each todo is its own commit on the current branch
- Commits prefixed by semantic type: `fix:`, `feat:`, `refactor:`, `chore:`
- No amends or force-pushes
- Final tag: `v0.3.0-alpha1` (if publish-ready)

## Success criteria
- [x] C3: config.py has no API key fields
- [ ] C1: First stdout line of companion is valid JSON-RPC
- [ ] C2: `/fusion` returns real model responses via OpenCode providers
- [ ] C4: `_get_opencode_api_keys()` removed from codebase
- [ ] Plugin compiles with 0 TypeScript errors
- [ ] All companion non-fusion features still work
