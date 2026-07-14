#!/usr/bin/env python3
"""
backfill_frontmatter.py — One-shot frontmatter backfill for legacy KB docs.

Uses Lark table format for metadata (Feishu markdown doesn't preserve YAML --- blocks).
"""

import re
import sys
import json
import argparse
import subprocess
from typing import Dict, List, Optional

LITERATURE_FOLDER_TOKEN = "<LIT_ROOT_TOKEN>"
PAPER_FOLDER_TOKEN = "<PAPER_FOLDER_TOKEN>"
ENTITY_FOLDER_TOKEN = "<ENTITY_FOLDER_TOKEN>"
CONCEPT_FOLDER_TOKEN = "<CONCEPT_FOLDER_TOKEN>"

KB_FOLDERS = [
    (LITERATURE_FOLDER_TOKEN, "文献学习根目录"),
    (PAPER_FOLDER_TOKEN, "论文"),
    (ENTITY_FOLDER_TOKEN, "实体"),
    (CONCEPT_FOLDER_TOKEN, "概念"),
]

REQUIRED_FIELDS = ("title", "type", "created", "sources")


def run_lark_cli(args: List[str], stdin_input: Optional[bytes] = None) -> str:
    """Execute lark-cli command. Pass stdin_input as bytes for --markdown -."""
    cmd = ["npx", "@larksuite/cli"] + args
    result = subprocess.run(cmd, capture_output=True, input=stdin_input)
    # Decode bytes immediately
    stdout = result.stdout.decode(errors='replace') if result.stdout else ''
    stderr = result.stderr.decode(errors='replace') if result.stderr else ''
    # Prefer stdout if it looks like valid output (non-empty, not just whitespace)
    if stdout.strip():
        return stdout
    # Otherwise return combined (stderr usually contains deprecation warnings)
    return stdout + stderr


def parse_frontmatter(markdown: str) -> Dict:
    """
    Parse frontmatter from doc body. Supports:
    - Lark table format (primary, used by this script)
    - YAML --- format (legacy, read-only)
    """
    result = {
        "present": False, "complete": False,
        "fields": [], "missing": list(REQUIRED_FIELDS), "values": {}
    }
    if not markdown:
        return result

    # Try Lark table format first
    if markdown.lstrip().startswith("<lark-table"):
        cells = re.findall(r'<lark-td>\s*(.*?)\s*</lark-td>', markdown, re.DOTALL)
        if cells and len(cells) >= 2:
            for i in range(0, len(cells) - 1, 2):
                key = cells[i].strip()
                val = cells[i + 1].strip()
                if key in REQUIRED_FIELDS:
                    result["values"][key] = val
                    result["fields"].append(key)
            result["present"] = True
            result["missing"] = [f for f in REQUIRED_FIELDS if f not in result["values"]]
            result["complete"] = len(result["missing"]) == 0
            t = result["values"].get("type")
            if t and t not in ("concept", "entity", "source-summary", "comparison"):
                result["missing"].append(f"type:{t}:invalid")
            return result

    # Fallback: YAML --- format
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return result
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return result
    result["present"] = True
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        result["fields"].append(key)
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            result["values"][key] = [v.strip().strip('"\'') for v in inner.split(",") if v.strip()]
        else:
            result["values"][key] = value
    result["missing"] = [f for f in REQUIRED_FIELDS if f not in result["values"]]
    result["complete"] = len(result["missing"]) == 0
    t = result["values"].get("type")
    if t and t not in ("concept", "entity", "source-summary", "comparison"):
        result["missing"].append(f"type:{t}:invalid")
    return result


def strip_frontmatter(markdown: str) -> str:
    """Remove frontmatter block (Lark table or YAML ---) from doc body."""
    if not markdown:
        return markdown
    if markdown.lstrip().startswith("<lark-table"):
        end = markdown.find("</lark-table>")
        if end != -1:
            return markdown[end + len("</lark-table>"):].lstrip()
    if markdown.lstrip().startswith("---"):
        lines = markdown.splitlines()
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip()
        return "\n".join(lines[1:]).lstrip() if lines else ""
    return markdown


def folder_to_type(folder_name: str) -> str:
    if "论文" in folder_name or "paper" in folder_name.lower():
        return "source-summary"
    if "实体" in folder_name or "entity" in folder_name.lower():
        return "entity"
    if "概念" in folder_name or "concept" in folder_name.lower():
        return "concept"
    return "entity"


def list_folder(folder_token: str) -> List[Dict]:
    params = json.dumps({"folder_token": folder_token})
    output = run_lark_cli([
        "drive", "files", "list",
        "--params", params,
        "--format", "json"
    ])
    try:
        data = json.loads(output)
        if data.get("code") == 0:
            return data.get("data", {}).get("files", [])
    except json.JSONDecodeError:
        pass
    return []


def fetch_doc(doc_token: str) -> Optional[Dict]:
    output = run_lark_cli([
        "docs", "+fetch",
        "--doc", doc_token,
        "--format", "json"
    ])
    try:
        data = json.loads(output)
        if data.get("ok"):
            return data.get("data", {})
    except json.JSONDecodeError:
        pass
    return None


def generate_frontmatter(title: str, folder_type: str, created_date: str) -> str:
    """Generate frontmatter as Lark table (YAML --- is stripped by Feishu markdown parser)."""
    return f"""<lark-table rows="4" cols="2" header-row="false" column-widths="200,500">
  <lark-tr>
    <lark-td>
      title
    </lark-td>
    <lark-td>
      {title}
    </lark-td>
  </lark-tr>
  <lark-tr>
    <lark-td>
      type
    </lark-td>
    <lark-td>
      {folder_type}
    </lark-td>
  </lark-tr>
  <lark-tr>
    <lark-td>
      created
    </lark-td>
    <lark-td>
      {created_date}
    </lark-td>
  </lark-tr>
  <lark-tr>
    <lark-td>
      sources
    </lark-td>
    <lark-td>
      []
    </lark-td>
  </lark-tr>
</lark-table>

"""


def walk_and_check() -> List[Dict]:
    from datetime import date
    today = date.today().isoformat()
    results = []

    for folder_token, folder_name in KB_FOLDERS:
        files = list_folder(folder_token)
        folder_type = folder_to_type(folder_name)

        for f in files:
            if f.get("type") != "docx":
                continue
            token = f.get("token", "")
            name = f.get("name", "未知文档")
            doc_data = fetch_doc(token)
            if not doc_data:
                print(f"  [WARN] Could not fetch {name} ({token})", file=sys.stderr)
                continue

            markdown = doc_data.get("markdown", "")
            fm = parse_frontmatter(markdown)

            results.append({
                "token": token,
                "name": name,
                "folder": folder_name,
                "folder_type": folder_type,
                "frontmatter": fm,
                "proposed": None if fm["complete"] else {
                    "title": name,
                    "type": folder_type,
                    "created": today,
                    "sources": [],
                    "frontmatter_table": generate_frontmatter(name, folder_type, today),
                }
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="Backfill frontmatter for legacy KB docs")
    parser.add_argument("--dry-run", action="store_true", help="Print proposed frontmatter, don't write")
    parser.add_argument("--apply", action="store_true", help="Apply frontmatter to all docs missing it")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.print_help()
        sys.exit(1)

    print("Walking 4 KB folders...", file=sys.stderr)
    docs = walk_and_check()

    complete = [d for d in docs if d["frontmatter"]["complete"]]
    missing = [d for d in docs if not d["frontmatter"]["complete"]]

    print(f"\nTotal docs: {len(docs)}", file=sys.stderr)
    print(f"Complete frontmatter: {len(complete)}", file=sys.stderr)
    print(f"Need backfill: {len(missing)}", file=sys.stderr)

    if args.dry_run:
        if missing:
            print("\n=== Proposed frontmatter (dry-run) ===\n")
            for d in missing:
                p = d["proposed"]
                print(f"# {d['name']} ({d['folder']}) [{d['token']}]")
                print(p["frontmatter_table"])
                print()
        else:
            print("\nAll docs already have complete frontmatter.", file=sys.stderr)
        return

    if args.apply:
        success = 0
        fail = 0
        for d in missing:
            p = d["proposed"]
            token = d["token"]
            fm_table = p["frontmatter_table"]
            output = run_lark_cli([
                "docs", "+fetch", "--doc", token, "--format", "json"
            ])
            try:
                doc_data = json.loads(output)
                if not doc_data.get("ok"):
                    print(f"  [FAIL] fetch {d['name']}", file=sys.stderr)
                    fail += 1
                    continue
                body = doc_data.get("data", {}).get("markdown", "")
                stripped = strip_frontmatter(body)
                new_body_bytes = (fm_table + stripped).encode('utf-8')
                update_output = run_lark_cli(
                    ["docs", "+update", "--doc", token, "--markdown", "-", "--mode", "overwrite"],
                    stdin_input=new_body_bytes
                )
                update_data = json.loads(update_output)
                if update_data.get("ok"):
                    print(f"  [OK] {d['name']}", file=sys.stderr)
                    success += 1
                else:
                    print(f"  [FAIL] update {d['name']}: {update_data}", file=sys.stderr)
                    fail += 1
            except Exception as e:
                print(f"  [FAIL] {d['name']}: {e}", file=sys.stderr)
                fail += 1

        print(f"\nBackfill complete: {success} succeeded, {fail} failed", file=sys.stderr)


if __name__ == "__main__":
    main()
