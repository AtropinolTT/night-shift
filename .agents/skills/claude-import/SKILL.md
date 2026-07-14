---
name: claude-import
description: >
  Import Claude Code sessions into Qoder CLI. Use when the user wants to
  bring conversation history from Claude Code into Qoder, migrate sessions,
  or run the claude-import script.
argument-hint: "<session-id|index|path> [--fork]"
user-invocable: true
version: "1.0.0"
---

# claude-import

Import Claude Code sessions into Qoder CLI so they become first-class Qoder
sessions, resumeable via `qodercli --resume <id>` or forkable via
`qodercli --fork-session --resume <id>`.

## How It Works

The script reads Claude Code session files from `~/.claude/projects/` (JSONL
format), converts the conversation (user messages, assistant replies, thinking
blocks, tool calls, tool results) into Qoder's native session format, and writes
them to `~/.qoder/projects/` with the proper `state.json`.

## Usage

Always use the script — do not attempt to convert session formats manually.

```
# List all available Claude Code sessions
python .agents/skills/claude-import/scripts/claude_import.py --list

# Import a session by index from the listing
python .agents/skills/claude-import/scripts/claude_import.py 87

# Import by full or partial UUID
python .agents/skills/claude-import/scripts/claude_import.py 9143a0c2-c828-4bcc-8f22-9221449357b2

# Import and immediately fork into a new Qoder session
python .agents/skills/claude-import/scripts/claude_import.py 87 --fork

# Import from an arbitrary JSONL file path
python .agents/skills/claude-import/scripts/claude_import.py /path/to/session.jsonl
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/claude_import.py` | Main import script |

## What Gets Converted

| Claude Code entry | Qoder entry |
|-------------------|-------------|
| `type: "user"` (non-meta) | `type: "user"` with `message.content` |
| `type: "assistant"` | `type: "assistant"` with thinking/text/tool_use blocks |
| `type: "system"` (local_command) | `type: "user"` with `tool_result` content |
| `custom-title` → session title | Used as Qoder session name |
| `mode`, `file-history-snapshot`, etc. | Skipped (metadata only) |

## Output

After import, the session appears in `qodercli --list-sessions` and can be
resumed or forked like any native Qoder session.

```
Resume with: qodercli --resume <session-id>
Fork with:   qodercli --fork-session --resume <session-id>
```
