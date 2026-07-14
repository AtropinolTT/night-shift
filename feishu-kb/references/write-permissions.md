# Write Permissions — Per-Mode lark-cli Whitelist

This file defines **which lark-cli write operations each mode is allowed to call**. The main context checks the current mode against this file before any write — if a command is not whitelisted for the active mode, the call is rejected and the user is told to use a different mode (or escalate to manual Feishu UI).

The general principle: **each mode writes only to its own surface, never touching the surfaces of other modes.** This isolates blast radius if a subagent returns a bad write plan.

## Mode Surface Map

| Mode | Owns | Does NOT touch |
|------|------|----------------|
| `qa` | PDFs (file uploads) + summary doc body (append only) | Concept/Entity/Paper doc creation, KB index, KB log, keyword lib, IM |
| `maintain` | Concept/Entity/Comparison doc creation + KB index/log updates + IM report | Paper doc creation, PDF uploads, keyword lib (only maintainer reports to KB log, not appends to keyword lib) |
| `update` | Paper doc creation + keyword lib append + IM report | Concept/Entity creation, KB index/log, PDF uploads |

**Hard-deny across all modes**: deleting any doc, moving docs between folders, renaming docs (titles must be set correctly at create time).

## qa Mode Whitelist (STAGE 1 ACTIVE)

`qa` is read-mostly. The only writes the librarian ever does are PDF pipeline side effects.

| Command | Args | Purpose | Folder/token target |
|---------|------|---------|---------------------|
| `drive +upload` | `--file <local.pdf> --folder-token <PDF_FOLDER_TOKEN> --name <crossref_title>.pdf` | Upload original paper PDF after CrossRef download | PDF folder only (`<PDF_FOLDER_TOKEN>`) |
| `docs +update` | `--doc <doc_token> --markdown "<new section>" --mode append` | Append PDF link section to the summary doc the user asked about | Current doc only — token must match one of the docs the user explicitly queried this turn |

**Hard-deny in qa**:
- `docs +create` — qa never creates new docs (defer to update / maintain).
- `drive +upload` to any folder other than `<PDF_FOLDER_TOKEN>`.
- `docs +update --mode replace` or `--mode prepend` — append-only, never clobber existing content.
- `docs +update` on a doc the user did not query.
- `im +messages-send` — qa never sends IM (defer to maintain / update completion reports).

If the user asks qa to "create a new entity doc for X" or "log this", respond with the routing hint:

> "qa is read-only. To create a new entity doc, use `feishu-kb 维护` (maintain mode) or `feishu-kb 检索` (update mode for papers)."

## maintain Mode Whitelist (STAGE 2 ACTIVE)

| Command | Args | Purpose | Target |
|---------|------|---------|--------|
| `docs +create` | `--folder-token <entity/concept folder> --title <name> --markdown <content>` | Create entity/concept/comparison doc | `<ENTITY_FOLDER_TOKEN>` (实体), `<CONCEPT_FOLDER_TOKEN>` (概念), `TBD_Stage1` (comparisons) |
| `docs +update` | `--doc <KB index/log token> --markdown <...> --mode append` | Append KB log entry or scaffold KG table | `<KB_INDEX_TOKEN>` (KB index), `<KB_LOG_TOKEN>` (KB log) |
| `docs +update` | `--doc <doc_token> --markdown <frontmatter> --mode replace` | Backfill frontmatter | Any doc token (from backfill_plan) |
| `im +messages-send` | `--user-id ou_... --msg-type text --content '{"text":"..."}'` | Completion report | `<IM_USER_ID>` |

**Hard-deny in maintain**:
- `docs +create` to `<PAPER_FOLDER_TOKEN>` (论文 folder) — update mode owns that
- `drive +upload` — qa owns PDF uploads
- `im +messages-send` to anyone other than `<IM_USER_ID>`
- Deleting, moving, or renaming any doc

## update Mode Whitelist (STAGE 3 ACTIVE)

| Command | Args | Purpose | Target |
|---------|------|---------|--------|
| `docs +create` | `--folder-token <PAPER_FOLDER_TOKEN> --title <FirstAuthor_Year_CleanedTitle> --markdown <content>` | Create paper summary doc | `<PAPER_FOLDER_TOKEN>` (论文 folder) only |
| `docs +update` | `--doc <KEYWORD_LIB_TOKEN> --markdown <new keywords> --mode append` | Append new keywords to keyword lib | `<KEYWORD_LIB_TOKEN>` (keyword library) only |
| `im +messages-send` | `--user-id ou_... --msg-type text --content '{"text":"..."}'` | Completion report | `<IM_USER_ID>` only |

**Hard-deny in update**:
- `docs +create` to any folder other than `<PAPER_FOLDER_TOKEN>` (论文) — maintain owns 实体/概念
- `docs +update` to any doc other than `<KEYWORD_LIB_TOKEN>` (keyword lib)
- `drive +upload` — qa owns PDF uploads; update does not handle PDFs
- Deleting, moving, or renaming any doc

## Enforcement Pattern (main context pseudo-code)

```python
ALLOWED = {
    "qa": {
        "drive +upload": {"folder_token": "<PDF_FOLDER_TOKEN>"},
        "docs +update": {"mode": "append", "doc_must_be_in_session": True},
    },
    "maintain": {
        "docs +create": {"folder_token_in": ["<ENTITY_FOLDER_TOKEN>",
                                              "<CONCEPT_FOLDER_TOKEN>",
                                              "TBD_comparisons"]},
        "docs +update": {"doc_must_be_in": ["<KB_INDEX_TOKEN>",
                                            "<KB_LOG_TOKEN>"]},
        "im +messages-send": {"user_id": "<IM_USER_ID>"},
    },
    "update": {
        "docs +create": {"folder_token": "<PAPER_FOLDER_TOKEN>"},
        "docs +update": {"mode": "append",
                         "doc_must_be": "<KEYWORD_LIB_TOKEN>"},
        "im +messages-send": {"user_id": "<IM_USER_ID>"},
    },
}

def check(mode, command, args):
    rule = ALLOWED.get(mode, {}).get(command)
    if rule is None:
        return False, f"{mode} mode cannot call {command}"
    for k, v in rule.items():
        actual = args.get(k)
        if isinstance(v, list) and actual not in v:
            return False, f"{command} {k}={actual} not in {v}"
        if isinstance(v, str) and actual != v:
            return False, f"{command} {k}={actual} != {v}"
    return True, "ok"
```

The main context calls `check()` immediately before any `lark-cli` invocation that mutates state. Read-only calls (`drive files list`, `docs +fetch`, `curl` to CrossRef/NCBI/etc.) are not gated.

## Why Not Just Pre-Permit Everything?

The `permissions.allow` block in `~/.claude/settings.json` (see SKILL.md §11) approves the **commands** (e.g., `npx @larksuite/cli docs +update*`). This file is the **second layer** that decides **which arguments** are allowed for which mode. Two layers:

1. **settings.json** — keeps the user from being prompted for every lark-cli call.
2. **write-permissions.md** — keeps a runaway qa subagent from accidentally creating a new paper doc.

If the second layer is removed, the user must review every write call manually — fine for 1 mode, painful for 3.

## See Also

- `search-scope.md` — folder tokens referenced in the whitelist
- `skill-activation.md` — how mode is set on entry
- SKILL.md §6 (Shared Rules) and §11 (Pre-Permissions)
