#!/usr/bin/env python3
"""Import Claude Code sessions into Qoder CLI.

Usage:
  python scripts/claude_import.py                          # list available Claude Code sessions
  python scripts/claude_import.py <session-id|index>        # import specific session
  python scripts/claude_import.py <session-id> --fork       # import and fork immediately
  python scripts/claude_import.py <path/to/session.jsonl>   # import from file path
"""

import json
import os
import sys
import uuid
import subprocess
from datetime import datetime, timezone
from pathlib import Path


QODER_PROJECTS = Path.home() / ".qoder" / "projects"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def get_qoder_project_dir():
    """Get the current Qoder project directory based on cwd."""
    cwd = os.getcwd()
    project_slug = "-" + cwd.lstrip("/").replace("/", "-")
    for p in QODER_PROJECTS.iterdir():
        if p.name.endswith(".jsonl") or p.is_file():
            continue
        if p.name == project_slug or project_slug.endswith(p.name) or p.name.endswith(project_slug):
            return p
    # Fallback: try matching by common path segments
    for p in QODER_PROJECTS.iterdir():
        if p.name.endswith(".jsonl") or p.is_file():
            continue
        cwd_parts = set(cwd.rstrip("/").split("/"))
        slug_parts = set(p.name.strip("-").split("-"))
        if cwd_parts & slug_parts:
            return p
    # Last resort: create
    candidate = QODER_PROJECTS / project_slug
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def find_claude_sessions():
    """List all available Claude Code sessions."""
    sessions = []
    for proj_dir in sorted(CLAUDE_PROJECTS.iterdir()):
        if not proj_dir.is_dir():
            continue
        for f in sorted(proj_dir.glob("*.jsonl"), key=os.path.getmtime, reverse=True):
            session_id = f.stem
            try:
                with open(f) as fh:
                    first = json.loads(fh.readline())
                    title = first.get("customTitle", session_id[:8])
            except (json.JSONDecodeError, StopIteration):
                title = session_id[:8]
            msg_count = 0
            try:
                with open(f) as fh:
                    for line in fh:
                        try:
                            entry = json.loads(line)
                            if entry.get("type") == "user" and not entry.get("isMeta"):
                                msg_count += 1
                        except json.JSONDecodeError:
                            pass
            except Exception:
                pass
            sessions.append({
                "id": session_id,
                "title": title,
                "messages": msg_count,
                "path": str(f),
                "project": proj_dir.name,
                "modified": os.path.getmtime(f),
            })
    return sessions


def convert_claude_to_qoder(claude_path):
    """Convert a Claude Code session JSONL to Qoder format entries."""
    qoder_entries = []
    session_id = str(uuid.uuid4())
    parent_uuid = None
    assistant_uuids = []

    with open(claude_path) as f:
        lines = f.readlines()

    # Extract title
    title = "Imported Session"
    for line in lines:
        try:
            entry = json.loads(line)
            if entry.get("type") == "custom-title":
                ct = entry.get("customTitle", "")
                if ct:
                    title = ct
                    break
        except json.JSONDecodeError:
            pass

    now = datetime.now(timezone.utc)
    ts = int(now.timestamp() * 1000)
    qoder_entries.append({
        "type": "runtime-config",
        "sessionId": session_id,
        "model": "claude-imported",
        "reasoningEffort": None,
        "contextWindow": None,
        "timestamp": ts,
    })

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry_type = entry.get("type")

        if entry_type == "user":
            msg = entry.get("message", {})
            content = msg.get("content", "")
            is_meta = entry.get("isMeta", False)
            if is_meta:
                continue

            user_uuid = f"user:{session_id}####import-{uuid.uuid4().hex[:8]}"
            ts_str = entry.get("timestamp", now.isoformat())

            user_entry = {
                "type": "user",
                "uuid": user_uuid,
                "timestamp": ts_str,
                "message": {"role": "user", "content": content},
                "permissionMode": "default",
                "origin": {"kind": "human"},
                "promptId": entry.get("promptId", str(uuid.uuid4())),
                "parentUuid": parent_uuid,
                "isSidechain": False,
                "cwd": entry.get("cwd", os.getcwd()),
                "sessionId": session_id,
                "userType": "external",
                "entrypoint": "cli",
                "version": "1.0.44",
            }

            if isinstance(content, list):
                user_entry["message"]["content"] = content

            qoder_entries.append(user_entry)
            parent_uuid = user_uuid

        elif entry_type == "assistant":
            msg = entry.get("message", {})
            content_blocks = msg.get("content", [])
            if not content_blocks:
                continue

            assistant_uuid = str(uuid.uuid4())
            assistant_uuids.append(assistant_uuid)
            ts_str = entry.get("timestamp", now.isoformat())

            processed_blocks = []
            for block in content_blocks:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "thinking":
                        processed_blocks.append({
                            "type": "thinking",
                            "thinking": block.get("thinking", ""),
                            "signature": block.get("signature", ""),
                        })
                    elif btype == "text":
                        processed_blocks.append({
                            "type": "text",
                            "text": block.get("text", ""),
                        })
                    elif btype == "tool_use":
                        processed_blocks.append({
                            "type": "tool_use",
                            "id": block.get("id", block.get("tool_use_id", f"call_import_{uuid.uuid4().hex[:8]}")),
                            "name": block.get("name", ""),
                            "input": block.get("input", {}),
                        })
                    else:
                        processed_blocks.append(block)
                else:
                    processed_blocks.append({"type": "text", "text": str(block)})

            stop_reason = msg.get("stop_reason")
            if stop_reason is None:
                has_tool = any(b.get("type") == "tool_use" for b in processed_blocks if isinstance(b, dict))
                stop_reason = "tool_use" if has_tool else "end_turn"

            msg_id = str(uuid.uuid4())
            assistant_entry = {
                "type": "assistant",
                "uuid": assistant_uuid,
                "timestamp": ts_str,
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-imported",
                    "stop_reason": stop_reason,
                    "stop_sequence": None,
                    "content": processed_blocks,
                },
                "parentUuid": parent_uuid,
                "isSidechain": False,
                "cwd": entry.get("cwd", os.getcwd()),
                "sessionId": session_id,
                "userType": "external",
                "entrypoint": "cli",
                "version": "1.0.44",
            }

            qoder_entries.append(assistant_entry)
            parent_uuid = assistant_uuid

        elif entry_type == "system":
            subtype = entry.get("subtype", "")
            if subtype == "local_command":
                content_str = entry.get("content", "")
                source_uuid = assistant_uuids[-1] if assistant_uuids else None
                if source_uuid:
                    system_uuid = str(uuid.uuid4())
                    ts_str = entry.get("timestamp", now.isoformat())
                    qoder_entries.append({
                        "type": "user",
                        "uuid": system_uuid,
                        "timestamp": ts_str,
                        "message": {
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": f"call_import_{uuid.uuid4().hex[:8]}",
                                "content": content_str,
                                "is_error": False,
                            }],
                        },
                        "sourceToolAssistantUUID": source_uuid,
                        "promptId": str(uuid.uuid4()),
                        "parentUuid": parent_uuid,
                        "isSidechain": False,
                        "cwd": entry.get("cwd", os.getcwd()),
                        "sessionId": session_id,
                        "userType": "external",
                        "entrypoint": "cli",
                        "version": "1.0.44",
                    })
                    parent_uuid = system_uuid

    qoder_entries.append({
        "type": "last-prompt",
        "sessionId": session_id,
        "lastPrompt": title,
    })
    qoder_entries.append({
        "type": "runtime-config",
        "sessionId": session_id,
        "model": "claude-imported",
        "reasoningEffort": None,
        "contextWindow": None,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
    })

    return session_id, title, qoder_entries


def write_qoder_session(project_dir, session_id, title, entries):
    """Write converted entries as a Qoder session."""
    jsonl_path = project_dir / f"{session_id}.jsonl"
    with open(jsonl_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    state_dir = project_dir / session_id
    state_dir.mkdir(exist_ok=True)
    state = {
        "sessionId": session_id,
        "revision": 1,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z",
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z",
        "data": {},
        "items": {},
        "workspaceDirectories": [os.getcwd()],
    }
    with open(state_dir / "state.json", "w") as f:
        json.dump(state, f, indent=2)
    return jsonl_path


def resolve_session(session_str):
    """Resolve session ID, index, or file path to a file path."""
    if os.path.isfile(session_str):
        return session_str

    if session_str.isdigit():
        sessions = find_claude_sessions()
        idx = int(session_str) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]["path"]
        print(f"Index out of range: {session_str} (1-{len(sessions)})")
        sys.exit(1)

    candidates = []
    for proj_dir in CLAUDE_PROJECTS.iterdir():
        for f in proj_dir.glob(f"{session_str}*.jsonl"):
            candidates.append(f)
    if len(candidates) == 1:
        return str(candidates[0])
    if len(candidates) > 1:
        print(f"Multiple sessions match '{session_str}':")
        for c in candidates:
            print(f"  {c.stem}")
        sys.exit(1)

    for proj_dir in CLAUDE_PROJECTS.iterdir():
        candidate = proj_dir / f"{session_str}.jsonl"
        if candidate.exists():
            return str(candidate)

    print(f"Session not found: {session_str}")
    sessions = find_claude_sessions()
    for s in sessions[:10]:
        print(f"  {s['id']}  ({s['title']})")
    if len(sessions) > 10:
        print(f"  ... and {len(sessions) - 10} more")
    sys.exit(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Import Claude Code sessions into Qoder CLI")
    parser.add_argument("session", nargs="?", help="Session ID, index number, or path to JSONL file")
    parser.add_argument("--resume", "-r", action="store_true", help="Resume the imported session")
    parser.add_argument("--fork", "-f", action="store_true", help="Fork the imported session into a new session")
    parser.add_argument("--list", "-l", action="store_true", help="List available Claude Code sessions")
    args = parser.parse_args()

    if args.list or (not args.session and sys.stdin.isatty()):
        sessions = find_claude_sessions()
        if not sessions:
            print("No Claude Code sessions found.")
            print(f"Looked in: {CLAUDE_PROJECTS}")
            return

        print(f"Found {len(sessions)} Claude Code session(s):")
        print()
        for i, s in enumerate(sessions, 1):
            age = datetime.fromtimestamp(s["modified"]).strftime("%Y-%m-%d %H:%M")
            print(f"  [{i}] {s['id']}")
            print(f"       Title: {s['title']}")
            print(f"       Messages: {s['messages']}")
            print(f"       Project: {s['project']}")
            print(f"       Modified: {age}")
            print()

        print("Import with: python .agents/skills/claude-import/scripts/claude_import.py <session-id|index>")
        return

    if not args.session:
        parser.print_help()
        return

    session_path = resolve_session(args.session)

    print(f"Importing: {session_path}")
    print("Converting to Qoder format...")

    project_dir = get_qoder_project_dir()
    session_id, title, entries = convert_claude_to_qoder(session_path)

    msg_count = sum(1 for e in entries if e.get("type") in ("user", "assistant"))
    jsonl_path = write_qoder_session(project_dir, session_id, title, entries)

    print(f"Session ID: {session_id}")
    print(f"Title: {title}")
    print(f"Entries: {len(entries)} (messages: {msg_count})")
    print(f"Written to: {jsonl_path}")
    print()
    print(f"Resume with: qodercli --resume {session_id}")
    print(f"Fork with:   qodercli --fork-session --resume {session_id}")

    if args.fork:
        print("\nForking session...")
        subprocess.run(["qodercli", "--fork-session", "--resume", session_id], check=False)
    elif args.resume:
        print("\nResuming session...")
        subprocess.run(["qodercli", "--resume", session_id], check=False)


if __name__ == "__main__":
    main()
