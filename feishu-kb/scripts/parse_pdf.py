#!/usr/bin/env python3
"""
PDF 解析脚本 - 提取文本、表格、图片、公式
支持 CLI 调用，适合 agent 使用

Usage:
    conda run -n marker python /path/to/parse_pdf.py <pdf_path> [-o <output_dir>] [--format json|md]
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 导入 PDF 解析库
import pdfplumber
import fitz  # pymupdf


def extract_text(pdf_path: str, pages: Optional[List[int]] = None) -> Dict[int, str]:
    """提取文本"""
    text_by_page = {}
    with pdfplumber.open(pdf_path) as pdf:
        page_range = pages if pages else range(len(pdf.pages))
        for i in page_range:
            if i < len(pdf.pages):
                text = pdf.pages[i].extract_text() or ""
                text_by_page[i + 1] = text  # 1-indexed
    return text_by_page


def extract_tables(pdf_path: str, pages: Optional[List[int]] = None) -> Dict[int, List[List]]:
    """提取表格 - 尝试多种策略取最优结果"""
    table_settings_list = [
        {},  # 默认
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    ]

    def is_valid_table(table: List[List]) -> bool:
        """过滤无效表格：至少2行3列，内容非空"""
        if not table or len(table) < 2:
            return False
        # 至少有一些行有3列以上（排除将段落误识别的假表格）
        valid_rows = 0
        for row in table:
            if row and sum(1 for c in row if c and c.strip()) >= 3:
                valid_rows += 1
        if valid_rows < 2:
            return False
        # 检查列数一致性（表格不应过于破碎）
        col_counts = [sum(1 for c in row if c and c.strip()) for row in table if row]
        if not col_counts:
            return False
        avg_cols = sum(col_counts) / len(col_counts)
        # 所有行列数偏差过大则视为碎片
        if max(col_counts) > avg_cols * 1.8:
            return False
        return True

    tables_by_page = {}
    with pdfplumber.open(pdf_path) as pdf:
        page_range = pages if pages else range(len(pdf.pages))
        for i in page_range:
            if i < len(pdf.pages):
                best_table = None
                for settings in table_settings_list:
                    tables = pdf.pages[i].extract_tables(table_settings=settings)
                    for table in tables:
                        if table and is_valid_table(table):
                            # 优先选择行数最多的有效表格
                            if best_table is None or len(table) > len(best_table):
                                best_table = table
                if best_table:
                    cleaned = []
                    for row in best_table:
                        if row:
                            cleaned_row = [cell.strip() if cell else "" for cell in row]
                            if any(c for c in cleaned_row):
                                cleaned.append(cleaned_row)
                    tables_by_page[i + 1] = [cleaned] if cleaned else []
                else:
                    tables_by_page[i + 1] = []
    return tables_by_page


def extract_images(pdf_path: str, output_dir: str, pages: Optional[List[int]] = None) -> Dict[int, List[str]]:
    """提取图片"""
    images_by_page = {}
    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    page_range = pages if pages else range(len(doc))

    for page_num in page_range:
        if page_num >= len(doc):
            break
        page = doc[page_num]
        images = page.get_images(full=True)
        page_key = page_num + 1
        image_paths = []

        for img_idx, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image['image']
            image_ext = base_image['ext']

            output_path = os.path.join(output_dir, f"page{page_key}_img{img_idx + 1}.{image_ext}")
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            image_paths.append(output_path)

        images_by_page[page_key] = image_paths

    doc.close()
    return images_by_page


def extract_formulas(text_by_page: Dict[int, str]) -> Dict[int, List[Dict]]:
    """提取 LaTeX 公式，返回带 confidence 标签的结构"""
    formulas_by_page = {}

    # LaTeX 公式模式
    latex_patterns = [
        r'\$([^\$]+)\$',           # 行内公式 $...$
        r'\$\$([^\$]+)\$\$',       # 块公式 $$...$$
        r'\\\[(.*?)\\\]',           # \[ ... \]
        r'\\\((.*?)\\\)',           # \( ... \)
    ]

    # 数学符号模式（检测文本中的数学表达式）
    math_symbol_patterns = [
        r'\d+[.,\d]*\s*[±]\s*\d+[.,\d]*',
        r'\d+[.,\d]*\s*/\s*\d+[.,\d]*',
        r'(?:sqrt|exp|log|ln|sin|cos|tan|abs|lim|min|max)\s*\(',
    ]

    def is_valid_formula(formula: str) -> bool:
        if len(formula) < 4 or len(formula) >= 200:
            return False
        if re.match(r'^\d{4}/\d+$', formula):
            return False
        if re.match(r'^\d+[\-]?\d*$', formula) and not re.search(r'[a-zA-Z]', formula):
            return False
        if re.search(r'10\.\d{4}', formula):
            return False
        if re.search(r'https?://|www\.', formula):
            return False
        if re.search(r'[a-zA-Z]{2,}_\d{4}', formula):
            return False
        return True

    for page_num, text in text_by_page.items():
        formulas = []
        seen = set()

        # 1. LaTeX 公式 (high confidence)
        for pattern in latex_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                formula = match.strip()
                if formula and len(formula) < 1000 and is_valid_formula(formula):
                    formulas.append({"text": formula, "confidence": "high"})

        # 2. 数学表达式（基于符号）(medium confidence)
        for pattern in math_symbol_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                formula = match.strip()
                if formula and len(formula) >= 4 and len(formula) < 200 and formula not in seen:
                    if is_valid_formula(formula):
                        formulas.append({"text": formula, "confidence": "medium"})
                        seen.add(formula)

        formulas_by_page[page_num] = formulas

    return formulas_by_page


def parse_pdf(
    pdf_path: str,
    output_dir: Optional[str] = None,
    output_format: str = "json",
    pages: Optional[List[int]] = None,
    extract_images_flag: bool = True
) -> Dict:
    """
    解析 PDF，返回结构化结果

    Args:
        pdf_path: PDF 文件路径
        output_dir: 图片输出目录
        output_format: 输出格式 "json" 或 "md"
        pages: 要解析的页码列表，None 表示全部
        extract_images_flag: 是否提取图片

    Returns:
        解析结果字典
    """
    if not os.path.exists(pdf_path):
        return {"error": f"File not found: {pdf_path}"}

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(pdf_path), "_pdf_extract")

    # 提取各类型内容
    text_by_page = extract_text(pdf_path, pages)
    tables_by_page = extract_tables(pdf_path, pages)

    images_by_page = {}
    if extract_images_flag:
        images_dir = os.path.join(output_dir, "_images")
        images_by_page = extract_images(pdf_path, images_dir, pages)

    formulas_by_page = extract_formulas(text_by_page)

    # 合并文本（用于快速预览）
    all_text = "\n".join(text_by_page.values())

    # 统计信息
    total_pages = len(text_by_page)
    total_tables = sum(len(tables) for tables in tables_by_page.values())
    total_images = sum(len(imgs) for imgs in images_by_page.values())
    total_formulas = sum(len(formulas) for formulas in formulas_by_page.values())

    result = {
        "pdf_path": pdf_path,
        "total_pages": total_pages,
        "text": text_by_page,
        "tables": tables_by_page,
        "images": images_by_page,
        "formulas": formulas_by_page,
        "stats": {
            "pages": total_pages,
            "tables": total_tables,
            "images": total_images,
            "formulas": total_formulas
        },
        "output_dir": output_dir
    }

    return result


def result_to_markdown(result: Dict) -> str:
    """将结果转换为 Markdown 格式"""
    md_lines = []

    md_lines.append(f"# PDF 解析结果: {os.path.basename(result['pdf_path'])}")
    md_lines.append("")
    md_lines.append("## 统计")
    md_lines.append(f"- 页数: {result['stats']['pages']}")
    md_lines.append(f"- 表格数: {result['stats']['tables']}")
    md_lines.append(f"- 图片数: {result['stats']['images']}")
    md_lines.append(f"- 公式数: {result['stats']['formulas']}")
    md_lines.append("")

    for page_num in sorted(result['text'].keys()):
        md_lines.append(f"## 第 {page_num} 页")
        md_lines.append("")

        # 文本
        text = result['text'][page_num]
        if text.strip():
            md_lines.append("### 文本")
            md_lines.append(text[:2000] + "..." if len(text) > 2000 else text)
            md_lines.append("")

        # 公式
        formulas = result['formulas'].get(page_num, [])
        if formulas:
            md_lines.append("### 公式")
            for i, formula in enumerate(formulas[:10], 1):  # 最多显示10个
                conf = formula.get("confidence", "high")
                conf_mark = " [medium]" if conf == "medium" else ""
                md_lines.append(f"{i}. `${formula['text']}$`{conf_mark}")
            md_lines.append("")

        # 表格
        tables = result['tables'].get(page_num, [])
        if tables:
            md_lines.append("### 表格")
            for i, table in enumerate(tables[:5], 1):  # 最多显示5个
                md_lines.append(f"**表格 {i}** ({len(table)} 行 x {len(table[0]) if table else 0} 列)")
                # 显示前3行
                for row in table[:3]:
                    md_lines.append("| " + " | ".join(str(cell)[:30] for cell in row) + " |")
                if len(table) > 3:
                    md_lines.append(f"... ({len(table) - 3} more rows)")
                md_lines.append("")

        # 图片
        images = result['images'].get(page_num, [])
        if images:
            md_lines.append("### 图片")
            for img in images:
                md_lines.append(f"![{os.path.basename(img)}]({img})")
            md_lines.append("")

        md_lines.append("---")
        md_lines.append("")

    return "\n".join(md_lines)


def main():
    parser = argparse.ArgumentParser(
        description="PDF 解析脚本 - 提取文本、表格、图片、公式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # 解析 PDF 并输出 JSON
    conda run -n marker python parse_pdf.py document.pdf

    # 解析指定页码并输出 Markdown
    conda run -n marker python parse_pdf.py document.pdf -o output --format md --pages 1 2 3

    # 只提取文本（不提取图片，更快）
    conda run -n marker python parse_pdf.py document.pdf --no-images
        """
    )

    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("-o", "--output-dir", help="输出目录", default=None)
    parser.add_argument("-f", "--format", choices=["json", "md"], default="json", help="输出格式")
    parser.add_argument("--pages", nargs="+", type=int, help="指定页码（1-indexed）", default=None)
    parser.add_argument("--no-images", action="store_true", help="不提取图片")

    args = parser.parse_args()

    # 处理页码（转换为 0-indexed）
    pages = None
    if args.pages:
        pages = [p - 1 for p in args.pages]

    # 解析
    result = parse_pdf(
        args.pdf_path,
        output_dir=args.output_dir,
        extract_images_flag=not args.no_images,
        pages=pages
    )

    # 输出
    if args.format == "md":
        output = result_to_markdown(result)
        print(output)
    else:
        output = json.dumps(result, ensure_ascii=False, indent=2)
        print(output)

    # 保存到文件
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(args.pdf_path))[0]

        if args.format == "md":
            output_path = os.path.join(args.output_dir, f"{base_name}.md")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result_to_markdown(result))
        else:
            output_path = os.path.join(args.output_dir, f"{base_name}.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n结果已保存到: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()