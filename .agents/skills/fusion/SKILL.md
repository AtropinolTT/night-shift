---
name: fusion
description: >
  Multi-model fusion dispatch. Dispatch a prompt to 2-3 AI models in parallel and
  synthesize a fused answer. Use when the user types `/fusion "prompt"` or asks
  to compare model responses, do model fusion, or dispatch to multiple models.
---

# Fusion Dispatch

## Trigger

User types `/fusion "<prompt>"` or asks to compare model responses / do model fusion.

Speed flags:
- `/fusion --fast "prompt"` — skip synthesis, show raw results immediately
- `/fusion --timeout=30 "prompt"` — set per-model deadline (default 45s)
- `/fusion --reset "prompt"` — force new sessions, ignore cache

## Workflow

### 1. Check session memory

Scan todos for BOTH:
- `[fusion] Model preference:` → determines which models to dispatch
- `[fusion] Sessions: flash=ses_A, pro=ses_B` → cached session IDs

- **Preference found** → use it. Proceed.
- **Not found** → Step 2.

### 2. First-time preference

Ask via `question`: Flash + Pro (Recommended), Pro only, Flash only, or Custom.

Record: `todowrite: [fusion] Model preference: flash+pro`

### 3. Parse options

Extract from prompt (remove before dispatching):
- `--fast` → skip synthesis entirely
- `--timeout=N` → per-model deadline in seconds (default: 45)
- `--reset` → force fresh sessions, ignore cache

### 4. Dispatch in parallel

**Two paths based on session cache:**

| Condition | Path | Action |
|---|---|---|---|
| Cache found AND no `--reset` | **FAST** | `bash(opencode run --session ses_X --model M "P" --format json)` — ~3-5s |
| No cache OR `--reset` | **FRESH** | `task(category=..., ..., prompt=P)` per model — ~50s |

**Map model → --model and session:**

| Label | `--model` value | Session |
|---|---|---|
| `flash` | `deepseek/deepseek-v4-flash` | from `[fusion] Sessions:` |
| `pro` | `deepseek/deepseek-v4-pro` | from `[fusion] Sessions:` |

**FRESH path** (first call or --reset):
1. Dispatch via `task(category=quick, run_in_background=true, prompt="<prompt>")` for flash
2. Dispatch via `task(category=unspecified-high, run_in_background=true, prompt="<prompt>")` for pro
3. Collect session IDs from task metadata (the `<session_id>` field)
4. Record: `todowrite: [fusion] Sessions: flash=ses_X, pro=ses_Y`
5. Wait for bg tasks, collect results

**FAST path** (cached sessions — refresh if all sessions are dead):
1. Dispatch ALL model calls in ONE message via parallel `bash()` calls:
   ```
   bash(command="opencode run --session ses_FLASH --model deepseek/deepseek-v4-flash \"<prompt>\" --format json", timeout={N*1000})
   bash(command="opencode run --session ses_PRO --model deepseek/deepseek-v4-pro \"<prompt>\" --format json", timeout={N*1000})
   ```
2. Parse each JSON output: find the last `{"type":"text","part":{"type":"text","text":"..."}}` and extract `text`.
3. If ALL `bash()` calls fail/timeout → sessions dead. Clear the sessions todo, fall back to FRESH path.
4. IMPORTANT: NEVER use `task(task_id=...)` to continue sessions. It corrupts them. Use `opencode run --session` exclusively.

### 6. Skip synthesis if...

Skip synthesis when ANY is true:
- `--fast` flag was used
- <2 models responded successfully
- All responses **agree** (similar length ±30% AND similar first 100 chars — use your judgment)

Otherwise, dispatch synthesis:

```
task(
  prompt="Synthesize to one coherent answer:\n\n---\n\n{all responses}",
  category="unspecified-high",
  run_in_background=false
)
```

### 7. Format output

```
**EXPERIMENTAL — Model Fusion (v2-fast)**

**Prompt:** <prompt>
**Mode:** <fast | synthesized | single>
**Sessions:** <preloaded | new>

| Model | Response | Duration |
|-------|----------|----------|
| deepseek-v4-flash | ... | 15s |
| deepseek-v4-pro | TIMED OUT | >=45s |

### Fused Answer
<synthesis result — or "[--fast mode]" — or lone model response>
```

### 8. Error handling

Mark timeouts/errors in the table. If ALL fail, report failure.

## Model mapping

| `task()` param | Model |
|---|---|
| `category="quick"` | deepseek-v4-flash |
| `category="unspecified-high"` | deepseek-v4-pro |
