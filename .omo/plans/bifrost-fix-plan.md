# bifrost-fix-plan - Work Plan

## TL;DR (For humans)
Fix the 4 remaining issues preventing bifrost from working end-to-end: (1) companion path is fragile (breaks when installed via npm), (2) slash commands don't work (OpenCode doesn't route `/fusion` through `command.execute.before`), (3) classifier blocks bash commands — prevents normal LLM tool usage, (4) source/cache mismatch — rebuilt code needs to sync to OpenCode's npm cache. After fixes, `/fusion "prompt"` will dispatch prompts through OpenCode's providers, the companion will serve all non-fusion features, and the classifier will allow safe bash commands.

## Scope
**IN:**
- A: Permanent companion path fix (env var + absolute fallback in source; rebuild + sync to caches)
- B: Slash command fix (test `command.execute.before` hook, add fallback `chat.message` interceptor)
- C: Classifier fix (add bash to allowlist pre-filter OR add configurable command allowlist)
- D: Cache sync fix (script or automation to keep npm caches in sync with source rebuilds)

**OUT:**
- No changes to non-bifrost code
- No workspace-wide config changes
- No OpenCode core modifications

## Verification strategy
- A: Companion connects on restart without "companion exited with code 2" error
- B: `/fusion "hello"` produces the EXPERTIMENTAL banner with model responses
- C: `bash("echo test")` executes successfully (not blocked by classifier)
- D: Source edit → rebuild → OpenCode restart picks up changes without manual cache patching

## Execution strategy

### Dependency graph
```
A (path fix) ──→ B (slash commands) ──→ C (classifier) ──→ D (cache sync)
```

A is independent. B depends on A (companion must connect for MCP fallback). C depends on A. D is the cleanup that ties everything together.

### Wave 1: A — Permanent companion path fix
- Change `COMPANION_SCRIPT` in source to try `process.env.BIFROST_COMPANION_PATH` then absolute path
- Add `import fs from "node:fs"` to verify path exists
- Rebuild: `npm run build`
- Sync dist to both npm caches: `~/.cache/opencode/packages/bifrost-plugin/node_modules/bifrost-plugin/dist/` and `~/.cache/opencode/packages/bifrost-plugin@latest/node_modules/bifrost-plugin/dist/`

### Wave 2: B — Slash command fix
- Test `/asdf1234` — does "Unknown command" appear? If yes: hook works but `input.command` doesn't match. If no: hook never fires.
- If hook works but doesn't match: log `input.command` to console to see exact value
- If hook doesn't fire: test `"chat.message"` hook as fallback ([intercept `^/fusion` in user messages])
- Fix the source code accordingly

### Wave 3: C — Classifier fix
- The classifier's pre-filter allows Read/Glob/Grep/lsp_* but blocks Bash
- Add bash to the pre-filter allowlist OR add a configuration option
- Alternative: add a `BIFROST_ALLOW_BASH=1` env var that skips classification for bash
- Fix source code accordingly

### Wave 4: D — Cache sync
- Add a `postbuild` npm script that copies dist to both cache locations
- OR add a `Makefile` target
- OR document the manual sync steps

## Todos

### [x] T1: Permanent companion path fix
**References**: `bifrost/plugin/index.ts:7-9`, `bifrost/plugin/dist/index.js:7`
**Acceptance**: ✅ Companion connects without "exited with code 2" error
**QA**: Path uses `process.env.BIFROST_COMPANION_PATH || "/absolute/path"` with `import fs`
**Commit**: `fix(plugin): use env var + absolute path for companion script`

### [x] T2: Slash command fix — switched to `chat.message` hook
**References**: `bifrost/plugin/index.ts:1089`, `@opencode-ai/plugin/dist/index.d.ts:187`
**Acceptance**: `/fusion "hello"` should produce EXPERIMENTAL banner (needs restart to confirm)
**QA**: `/fusion "hello"` in OpenCode shows fusion output

### [x] T3: Classifier shows as chat messages instead of errors
**References**: `bifrost/plugin/index.ts:653-678`, `bifrost/plugin/dist/index.js:443-459`
**Acceptance**: ✅ DENY now shows permission prompt (output.allow=false) instead of throw Error
**QA**: Bash commands show as chat prompt "denied by classifier" with Allow/Deny buttons

### [x] T4: Cache sync automation
**References**: Both npm cache locations, `bifrost/plugin/package.json`
**Acceptance**: ✅ `postbuild` script in package.json copies dist to both caches
**QA**: Run `npm run build && npm run postbuild` — verify cache JS timestamp matches source
**Commit**: `chore(plugin): add postbuild cache sync`

## Final verification wave
F1: Plugin loads without errors on OpenCode startup
F2: `/fusion "hello"` returns real model responses
F3: `/goal "test"` shows goal usage
F4: Bash commands execute normally
F5: All other commands (review, explain, commit, test, audit-permissions) work

## Commit strategy
- Each todo is its own commit
- Commits prefixed by type: `fix:`, `chore:`
- No amends or force-pushes

## Success criteria
- [x] Companion connects without errors
- [x] `/fusion` produces output (code done — pending user restart to confirm)
- [x] Bash shows permission prompt instead of error (code done — pending user restart to confirm)
- [x] Cache stays in sync with source (postbuild script added)
