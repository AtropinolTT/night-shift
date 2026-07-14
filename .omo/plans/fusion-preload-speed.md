# Fusion Preload Speed

## Goal

Make `/fusion` fast by preloading subagent sessions. First call ~50s (one-time), subsequent calls ~5-10s.

## How it works

`task()` creates a new subagent session each call — that's 30-40s of bootstrap overhead. But `task(task_id="ses_...")` **continues** an existing session with zero bootstrap. So we cache session IDs after the first call and reuse them.

## Changes

### 1. Update `fusion/SKILL.md` — add preloaded dispatch

Replace Steps 1-4 with:

```
### 1. Check session memory

Scan todos for:
- `[fusion] Model preference:` → which models
- `[fusion] Sessions:` → `flash=ses_X, pro=ses_Y` etc

### 2. First-time preference (if missing)

`question`: Flash + Pro, Pro only, Flash only, Custom.
Record: `todowrite: [fusion] Model preference: flash+pro`

### 3. Parse options

Extract: `--fast`, `--timeout=N`, `--reset`. Remove from prompt.

### 4. Dispatch (PRELOAD)

Map preference:

| Preference | Labels | Categories |
|---|---|---|
| flash+pro | flash, pro | quick, unspecified-high |
| pro-only | pro | unspecified-high |
| flash-only | flash | quick |
| custom: a,b,... | flash→quick, rest→unspecified-high | |

**Has cached sessions AND no --reset?**
- Parse `[fusion] Sessions: flash=ses_X, pro=ses_Y`
- `task(task_id=ses_X, prompt="...", run_in_background=true)` → FAST (~5s)

**No cache (first call or --reset)?**
- `task(category=..., prompt="...", run_in_background=true)` → slow (~50s)
- Store returned session IDs: `todowrite: [fusion] Sessions: flash=ses_X, pro=ses_Y`
```

Steps 5-8 remain unchanged (collect, skip-synthesis, format, errors).

### 2. New flags

- `--reset` → discard cached sessions, create fresh ones
- `--fast` → skip synthesis (existing)
- `--timeout=N` → per-model deadline (existing)

### 3. Output update

Add `Sessions: preloaded | new` line to show status.

## Verification

- First `/fusion "test"` → ~50s, stores sessions
- Second `/fusion "test"` → ~5-10s, uses preloaded sessions
- `/fusion --reset "test"` → ~50s, forces new sessions

## File changes

| File | Action |
|---|---|
| `.agents/skills/fusion/SKILL.md` | Replace Steps 1-4 with preload logic, add `--reset` flag |
