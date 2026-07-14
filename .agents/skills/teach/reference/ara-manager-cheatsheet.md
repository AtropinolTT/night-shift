# /ara-manager — Quick Reference

## 👀 Inspect (Read-only)

| Command | What it does | Example |
|---------|-------------|---------|
| `status` | Dashboard — claims, staged obs, tree stats | `/ara-manager status --json` |
| `briefing` | Full sitrep — last session, open threads, stale obs | `/ara-manager briefing` |
| `tree` | Print exploration DAG | `/ara-manager tree --node N12 --depth 3` |

## ✏️ Record (Write)

| Command | When | Example |
|---------|------|---------|
| `log decision` | Deliberate choice | `log decision "Use X over Y" --provenance user` |
| `log experiment` | Ran an experiment | `log experiment "R11 HPO: params..." --provenance ai-executed` |
| `log dead_end` | Path that didn't work | `log dead_end "PDI R²≈0 — artifact" --provenance user` |
| `log pivot` | Changed direction | `log pivot "RF → XGBoost" --provenance user` |
| `log question` | Open research question | `log question "Does uncertainty help AL?" --provenance ai-suggested` |
| `add-claim` | Stage a falsifiable assertion | `add-claim "EE R²=0.93" --bound-to N30,N45` |

## 🔄 Advance (Promote)

| Command | What it does | Example |
|---------|-------------|---------|
| `crystallize O{XX} --via <signal>` | Promote staged obs into logic/ | `crystallize O114 --via resolution` |
| `advance-claim C{XX} <status>` | Update claim status | `advance-claim C07 supported --note "54 tests pass"` |
| `revise-claim C{XX}` | Rewrite statement/rationale | `revise-claim C07 --statement "..."` |

## 🤖 Automated (Batch)

| Command | What it does |
|---------|-------------|
| `update with docs/` | Scan files → extract claims/decisions → stage |
| `update claims` | Suggest which claims can advance |
| `update obs` | Suggest which observations can crystallize |
| `compile docs/` | 3-pass deep read + stage + optional crystallize |

## 🛡️ Quality

| Command | What it does |
|---------|-------------|
| `validate` | Seal Level 1 — 17 structural checks |
| `review` | Seal Level 2 — epistemic audit (delegates) |

## Closure Signals

| Signal | When |
|--------|------|
| `affirmation` | You explicitly said yes |
| `resolution` | Experiment completed, you commented |
| `abandonment` | No events for 5+ turns |
| `commitment` | Downstream artifact depends on it |

## Provenance Values

| Value | Meaning |
|-------|---------|
| `user` | You said it / made the call |
| `ai-suggested` | Claude proposed, not confirmed (🥇 safe default) |
| `ai-executed` | Claude ran the experiment |
| `user-revised` | Claude proposed, you edited |

## Claim Status Flow

```
hypothesis → testing → supported
hypothesis → testing → weakened
hypothesis → refuted          (terminal)
any → withdrawn               (terminal)
any → revised                 (resets to hypothesis/testing)
```

---

**Habit:** Start each session with `briefing` → `tree --type question`.
End each session with `log experiment "..."`.
