#!/usr/bin/env python3
"""
feishu-kb fetch_doc.py
文档抓取脚本，支持引用链路跟随（最多5层）和循环检测

Token constants must match references/search-scope.md — that file is the
single canonical source. If a token changes, edit search-scope.md first,
then update the matching constant here.
"""

import re
import subprocess
import json
import sys
from typing import Optional, Set, List, Dict

# Token constants — keep in sync with references/search-scope.md
MAX_DEPTH = 5
LITERATURE_FOLDER_TOKEN = "<LIT_ROOT_TOKEN>"
PAPER_FOLDER_TOKEN = "<PAPER_FOLDER_TOKEN>"
ENTITY_FOLDER_TOKEN = "<ENTITY_FOLDER_TOKEN>"
CONCEPT_FOLDER_TOKEN = "<CONCEPT_FOLDER_TOKEN>"
PDF_FOLDER_TOKEN = "<PDF_FOLDER_TOKEN>"
KB_INDEX_TOKEN = "<KB_INDEX_TOKEN>"
KB_LOG_TOKEN = "<KB_LOG_TOKEN>"
KEYWORD_LIB_TOKEN = "<KEYWORD_LIB_TOKEN>"
IM_USER_ID = "<IM_USER_ID>"
CONCEPT_CACHE_MRNA = "<CACHE_MRNA_TOKEN>"
CONCEPT_CACHE_LNP = "<CACHE_LNP_TOKEN>"
CONCEPT_CACHE_GENE_EDIT = "<CACHE_GENE_EDIT_TOKEN>"

KB_FOLDERS = [PAPER_FOLDER_TOKEN, ENTITY_FOLDER_TOKEN, CONCEPT_FOLDER_TOKEN]


def run_lark_cli(args: List[str]) -> str:
    """执行 lark-cli 命令"""
    cmd = ["npx", "@larksuite/cli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Try stdout alone first (some commands emit deprecation warnings to stderr
    # which corrupts JSON when concatenated with stdout).
    # If stdout is empty or looks like stderr, fall back to combined.
    if result.stdout.strip():
        return result.stdout
    return result.stdout + result.stderr


def search_folder(folder_token: str, query: str = "") -> List[Dict]:
    """搜索文件夹内容"""
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


def fetch_document(doc_token: str) -> Optional[Dict]:
    """抓取单个文档内容"""
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


def extract_doc_title(doc_data: Dict) -> str:
    """提取文档标题"""
    return doc_data.get("title", "未知文档")


def extract_doc_url(doc_data: Dict, doc_token: str) -> str:
    """生成文档飞书链接"""
    return f"https://your-workspace.feishu.cn/docx/{doc_token}"


def build_index_map() -> Dict[str, str]:
    """构建知识库索引映射（文档名 -> token）"""
    # 从知识库索引文档获取
    doc_data = fetch_document(KB_INDEX_TOKEN)

    index_map = {}
    if doc_data:
        markdown = doc_data.get("markdown", "")
        # 简单解析：搜索 | 实体_xxx | 或 | 概念_xxx | 模式
        # 匹配表格中的文档名
        pattern = r'[｜|](实体_[^｜|]+|[^｜|]+_[^｜|]+)[｜|]'
        matches = re.findall(pattern, markdown)
        for match in matches:
            if "_" in match and ("实体_" in match or "概念_" in match or "论文" in match):
                # 这里简化处理，实际应该解析完整表格
                pass

    # 也搜索实体文件夹
    files = search_folder(ENTITY_FOLDER_TOKEN)
    for f in files:
        if f.get("type") == "docx":
            name = f.get("name", "")
            token = f.get("token", "")
            if name.startswith("实体_"):
                index_map[name] = token

    return index_map


def fetch_with_citations(
    doc_token: str,
    visited: Optional[Set[str]] = None,
    depth: int = 0
) -> Dict[str, any]:
    """
    抓取文档并跟随引用链路

    Args:
        doc_token: 文档 token
        visited: 已访问文档集合（用于循环检测）
        depth: 当前深度

    Returns:
        包含文档内容和引用链路的字典
    """
    if visited is None:
        visited = set()

    # 循环检测
    if doc_token in visited:
        return {"skipped": True, "reason": "循环引用"}
    if depth >= MAX_DEPTH:
        return {"skipped": True, "reason": "超过最大深度"}

    visited.add(doc_token)

    # 抓取文档
    doc_data = fetch_document(doc_token)
    if not doc_data:
        return {"error": f"无法获取文档 {doc_token}"}

    result = {
        "token": doc_token,
        "title": extract_doc_title(doc_data),
        "url": extract_doc_url(doc_data, doc_token),
        "markdown": doc_data.get("markdown", ""),
        "references": []
    }

    # 提取文档中的引用（简化版：搜索文档名模式）
    markdown = doc_data.get("markdown", "")

    # 匹配 [[文档名]] 或 "详见 xxx" 模式
    citation_patterns = [
        r'\[([^\]]+)\]',  # [文档名]
        r'详见[^\n]+([实体_[^\n]+|概念_[^\n]+)',
        r'参考[^\n]+([实体_[^\n]+|概念_[^\n]+)',
    ]

    # 从索引获取文档名映射
    index_map = build_index_map()

    # 搜索实体文件夹获取更多映射
    files = search_folder(ENTITY_FOLDER_TOKEN)
    for f in files:
        if f.get("type") == "docx":
            index_map[f.get("name", "")] = f.get("token", "")

    # 搜索概念文件夹
    files = search_folder(CONCEPT_FOLDER_TOKEN)
    for f in files:
        if f.get("type") == "docx":
            index_map[f.get("name", "")] = f.get("token", "")

    # 搜索论文文件夹
    files = search_folder(PAPER_FOLDER_TOKEN)
    for f in files:
        if f.get("type") == "docx":
            index_map[f.get("name", "")] = f.get("token", "")

    # 跟随引用
    for doc_name, ref_token in index_map.items():
        if doc_name in markdown and ref_token != doc_token:
            # 递归抓取引用文档
            ref_result = fetch_with_citations(ref_token, visited.copy(), depth + 1)
            if not ref_result.get("skipped"):
                result["references"].append(ref_result)

    return result


def search_knowledge_base(query: str) -> List[Dict]:
    """
    搜索知识库

    Args:
        query: 用户问题

    Returns:
        搜索结果列表
    """
    results = []

    # 搜索文献学习文件夹
    files = search_folder(LITERATURE_FOLDER_TOKEN)

    for f in files:
        name = f.get("name", "")
        token = f.get("token", "")
        ftype = f.get("type", "")

        # 如果是文件夹，递归搜索
        if ftype == "folder":
            sub_files = search_folder(token)
            for sf in sub_files:
                if query.lower() in sf.get("name", "").lower():
                    results.append(sf)
        else:
            # 文档匹配
            if query.lower() in name.lower():
                results.append(f)

    return results


def self_check() -> Dict:
    """
    Verify the KB root token is still valid. Called at every mode entry
    (qa, maintain, update) per references/search-scope.md §Self-Check.

    Returns:
        {"ok": True, "files_count": N} on success
        {"ok": False, "reason": "...", "hint": "..."} on failure
    """
    params = json.dumps({"folder_token": LITERATURE_FOLDER_TOKEN})
    output = run_lark_cli([
        "drive", "files", "list",
        "--params", params,
        "--format", "json"
    ])
    try:
        data = json.loads(output)
        code = data.get("code")
        files = data.get("data", {}).get("files", [])
        if code == 0 and len(files) > 0:
            return {"ok": True, "files_count": len(files)}
        return {
            "ok": False,
            "reason": f"code={code}, files={len(files)}",
            "hint": "KB root token may be stale. Update references/search-scope.md."
        }
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "reason": f"JSON decode error: {e}",
            "hint": "lark-cli output unparseable; check auth."
        }


REQUIRED_FRONTMATTER_FIELDS = ("title", "type", "created", "sources")
VALID_TYPES = ("concept", "entity", "source-summary", "comparison")


def parse_frontmatter(markdown: str) -> Dict:
    """
    Parse YAML-style frontmatter at the top of a doc.

    Frontmatter is delimited by lines containing only "---" (with optional
    trailing whitespace). Between the delimiters is key: value YAML.

    Returns:
        {
            "present": bool,           # delimiters found
            "complete": bool,          # all 4 required fields present
            "fields": [str],           # fields found
            "missing": [str],          # required fields missing
            "values": {field: value}   # raw values (str or list)
        }
    """
    result = {
        "present": False,
        "complete": False,
        "fields": [],
        "missing": list(REQUIRED_FRONTMATTER_FIELDS),
        "values": {},
    }
    if not markdown:
        return result

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
    fm_lines = lines[1:end_idx]
    for line in fm_lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        result["fields"].append(key)
        # Coerce list-shaped values (sources: ["..."], tags: [...])
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            result["values"][key] = [v.strip().strip('"\'') for v in inner.split(",") if v.strip()]
        else:
            result["values"][key] = value

    result["missing"] = [
        f for f in REQUIRED_FRONTMATTER_FIELDS if f not in result["values"]
    ]
    result["complete"] = len(result["missing"]) == 0

    # Type field must be one of the valid values
    t = result["values"].get("type")
    if t and t not in VALID_TYPES:
        result["missing"].append(f"type:{t}:invalid")

    return result


if __name__ == "__main__":
    # 命令行接口
    if len(sys.argv) < 2:
        print("Usage: fetch_doc.py <doc_token>")
        print("       fetch_doc.py --self-check   # verify KB root token")
        sys.exit(1)

    if sys.argv[1] == "--self-check":
        print(json.dumps(self_check(), ensure_ascii=False, indent=2))
        sys.exit(0)

    doc_token = sys.argv[1]
    result = fetch_with_citations(doc_token)

    # Attach frontmatter parse to top-level result
    if "markdown" in result:
        result["frontmatter"] = parse_frontmatter(result["markdown"])

    print(json.dumps(result, ensure_ascii=False, indent=2))