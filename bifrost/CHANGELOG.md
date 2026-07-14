# Changelog

## v0.2.1 (2026-07-11) — Security-Hardened Release

### Bug Fixes

#### Plugin (TypeScript)
- **BUG-1**: `/review` slash command now calls `skill_load("review")` instead of returning static help text.
- **BUG-2**: `/commit` slash command now calls `skill_load("git-master")` instead of returning static help text.
- **BUG-3**: `/test` slash command now calls `skill_load("tdd")` instead of returning static help text.
- **BUG-4**: Added default case for unrecognized slash commands — returns `"Unknown command: ..."` instead of silent no-op.
- **BUG-5**: Exported `CircuitBreaker` class from `mcp-relay.ts` for external use.
- **BUG-6**: Exported `validatePythonPath` function from `mcp-relay.ts` for testability.

#### Companion (Python)
- **BUG-7**: Added incremental schema migration support — `ALTER TABLE memories ADD COLUMN author TEXT` for existing databases.
- **BUG-8/9**: Fixed `_verify_permissions()` ordering — now checks permissions BEFORE applying `_chmod`, and returns `needs_fix` bool for self-healing.
- **BUG-10**: Removed `"dd"` from `_DESTRUCTIVE_NAME_SUBSTRINGS` — the 2-char substring caused false-positive DENY on tool names containing consecutive `d` characters (e.g., "readdeny"). Bash-level pattern `\bdd\s+if=` retains destructive coverage.
- **BUG-11**: Added NFKC normalization before `READ_ONLY_TOOLS` check — fullwidth Unicode homoglyphs like `"Ｒｅａｄ"` now correctly match the fast-path ALLOW.

### Other Changes
- Removed `cat` from default `allowlisted_bash_commands` (security hardening).
- Rebuilt TypeScript dist (`npx tsc`).
- Updated README to match actual config defaults.
