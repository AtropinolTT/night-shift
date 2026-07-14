---
name: feishu-kb
description: |
  飞书知识库智能问答 + 维护 + 检索一体化 skill。
  三种模式: qa (query / 默认) / maintain (lint) / update (ingest), 对应 Karpathy LLM Wiki 的 query/lint/ingest 三种操作。
  触发: 用户输入以 "feishu-kb" 开头;子命令 "维护/检索/查询" + 旧别名 "/loop-weekly-*";语义触发 "飞书知识库" / "本周文献检索"。
  librarian 子 agent (Explore 类型) 严格限制在知识库 4 个目录内搜索。
version: 1.0.0
triggers:
  - prefix: "feishu-kb"
  - subcommand: ["qa", "q", "查询", "maintain", "m", "维护", "update", "u", "检索"]
  - old_aliases: ["/loop-weekly-knowledge-base", "/loop-weekly-paper-search", "本周文献检索"]
  - semantic: "飞书知识库"
---

# feishu-kb Skill

飞书知识库智能问答助手,整合三种模式(查询 / 维护 / 检索)为一个 skill。

## 1. Overview

`feishu-kb` 是一个飞书知识库的统一入口,提供三种模式:

| 模式 | 旧 skill | Karpathy 映射 | 触发 | 主要动作 |
|------|---------|--------------|------|---------|
| `qa` (default) | 旧 feishu-kb | `query` | `feishu-kb <question>` | 读 KB、回答、引用跟随、PDF 解析 |
| `maintain` | feishu-kb-maintain (已删除) | `lint` | `feishu-kb 维护` | 去重、lint、frontmatter 回填、KG 索引 |
| `update` | feishu-kb-update (待删除) | `ingest` | `feishu-kb 检索` | 4 源 + RSS 检索、dedup、创建论文 doc |

三种模式共享一个 `librarian` 子 agent 和同一份搜索范围契约。Stage 1 (v1.0) 实现 `qa` 全功能 + `maintain` / `update` 框架(详细流程在 stage 2/3 落地)。

## 2. Karpathy LLM Wiki 对齐

本 skill 采纳 Karpathy "LLM Wiki" 模式的中等程度对齐:

- **三层架构**: `raw layer` (PDFs in `<PDF_FOLDER_TOKEN>`) / `wiki layer` (4 个 KB folders) / `schema layer` (`references/wiki-schema.md`)。
- **三种操作**: `query` (qa) / `lint` (maintain) / `ingest` (update)。
- **YAML frontmatter**: 每篇 wiki doc 顶部必须有 frontmatter,字段规则见 `references/wiki-schema.md`。
- **Wikilink 交叉引用**: 写入时 `[[concept-name]]` 渲染为飞书 doc 链接;读取时保留字面量。

不引入的 Karpathy 特性: schema 强制执行(只 lint,不阻止写)、自动 KG 重生成(只在维护时 scaffold)。

## 3. Installation

```bash
# 1. lark-cli (Feishu API; npx 即用,无需全局安装)
npm install -g @larksuite/cli   # 可选

# 2. 系统工具 (curation 与 dedup 脚本需要)
sudo apt-get install -y curl wget jq

# 3. PDF 解析 conda 环境 (qa 模式的 PDF parse pipeline 必需)
conda create -n marker python=3.11 -y
conda run -n marker pip install pdfplumber pymupdf

# 4. 验证
node --version
npx @larksuite/cli --version
conda run -n marker python -c "import pdfplumber, fitz; print('marker env OK')"
```

lark-cli 认证: 首次使用需 `npx @larksuite/cli auth login` 完成飞书 OAuth。

## 4. Trigger Table

主上下文在每次入口检查此表,按优先级匹配,首个命中即路由。

| Priority | Pattern | Mode | Notes |
|----------|---------|------|-------|
| 1 | `feishu-kb help` / `feishu-kb --help` / `feishu-kb -h` | (help) | 打印 trigger table;不做其他事 |
| 2 | `feishu-kb 维护` / `feishu-kb maintain` / `feishu-kb m` / `feishu-kb 维护 --dry-run` | `maintain` | `--dry-run` 跑子 agent 但跳过所有写操作 |
| 3 | `feishu-kb 检索` / `feishu-kb update` / `feishu-kb u` / `feishu-kb 检索 --query "..." --days 7` | `update` | 标志: `--query`, `--days`, `--journal`, `--mock-source` |
| 4 | `feishu-kb qa <question>` / `feishu-kb q <question>` / `feishu-kb <其他任何内容>` | `qa` | 默认;绝大多数查询落地此处 |
| 5 | `/loop-weekly-knowledge-base` | `maintain` | 旧别名,保留兼容 |
| 6 | `/loop-weekly-paper-search` / `weekly paper search` / `本周文献检索` | `update` | 旧别名,保留兼容 |

**裸 `feishu-kb` (无参数)**: 主上下文先用 `AskUserQuestion` 呈现三个选项让用户选择,再路由到对应模式(默认 `qa`)。不自动执行任何操作。选项:
- **查询知识库** (默认) — 问问题,跟随引用,解析 PDF
- **维护知识库** — dedup + lint + frontmatter 回填 + KG scaffold + IM 报告
- **检索新论文** — 4 源 + RSS 搜索,d edup,创建论文摘要

**裸 `feishu-kb` 加未识别参数** 默认 `qa`(rule 4)。例: `feishu-kb mRNA` → `qa` 模式,查询 "mRNA"。

详见 `references/skill-activation.md`。

## 5. Mode Summary

| 模式 | Verb | 写面 (lark-cli) | 子 agent | 输出 |
|------|------|----------------|----------|------|
| `qa` | query | `drive +upload` (PDF folder only) + `docs +update --mode append` (当前 doc) | librarian | 自然语言回答 + 飞书链接 |
| `maintain` | lint | `docs +create` (实体/概念/comparisons) + `docs +update` (KB index/log) + `im +messages-send` | librarian (KB index 扫描) + maintainer (分析) | 结构化分析报告 → 写动作 |
| `update` | ingest | `docs +create` (论文 folder only) + `docs +update --mode append` (keyword lib) + `im +messages-send` | librarian (历史查询) + collector (分析) | 新建 doc 列表 + IM 报告 |

写面详细清单见 `references/write-permissions.md`。

## 6. Shared Rules (强制)

### 6.1 4-folder 搜索范围 (所有模式、所有 agent)

**只允许搜索以下 4 个目录:**

| 目录 | Token | 说明 |
|------|-------|------|
| 文献学习 (根) | <LIT_ROOT_TOKEN> | 主目录 |
| 论文 | <PAPER_FOLDER_TOKEN> | 子文件夹 |
| 实体 | <ENTITY_FOLDER_TOKEN> | 子文件夹 |
| 概念 | <CONCEPT_FOLDER_TOKEN> | 子文件夹 |

其他 token: PDF folder `<PDF_FOLDER_TOKEN>`;KB 索引 `<KB_INDEX_TOKEN>`;KB log `<KB_LOG_TOKEN>`;keyword lib `<KEYWORD_LIB_TOKEN>`;IM user `<IM_USER_ID>`。完整表格见 `references/search-scope.md`。

### 6.2 禁止命令 (所有模式)

- **`lark-cli docs +search` / `lark-cli drive +search`**: 搜索整个云盘,超出 4-folder 范围。
- **`lark-cli drive +export --file-extension pdf` (用于原始论文 PDF)**: 导出的是飞书 docx 转换的 PDF,不是原始论文。要原始论文用 CrossRef PDF link (`references/crossref-helper.md`)。
- **`mcp__pubmed__*` / `mcp__arxiv__*` / `mcp__chrome_devtools__*`**: 环境中不可用。用 curl + RSS 替代 (`references/paper-search.md`, stage 3)。

### 6.3 搜索模板

```bash
npx @larksuite/cli drive files list --params '{"folder_token":"<TOKEN>"}' --format json
```

`<TOKEN>` 必须是 4-folder 之一的根 token。

### 6.4 Subagent 架构

| Agent | subagent_type | 用途 | 调用方 |
|-------|---------------|------|--------|
| `librarian` | Explore | 读 KB;qa 主要 + maintain 的 KB index/keyword 扫描 | qa, maintain |
| `maintainer` | Explore | 跑 7 步维护分析;只返回 JSON,不写 | maintain |
| `collector` | Explore | 4 源 + RSS 聚合、dedup;只返回 JSON,不写 | update |

**写入执行规则**: subagent 返回 JSON,主上下文执行所有 `lark-cli` 写动作 (`docs +create` / `docs +update` / `im +messages-send`)。这保证 main context 始终有 mode-isolated write 控制权。

### 6.5 Self-Check (每个 mode 入口)

```bash
python3 ~/.claude/skills/feishu-kb/scripts/fetch_doc.py --self-check
```

返回 `{"ok": true, "files_count": N}` 继续;否则 halt 并指向 `references/search-scope.md`。处理 token staleness。

### 6.6 Frontmatter (每篇 wiki doc)

`references/wiki-schema.md` 是单一来源。必填字段: `title`, `type` (concept|entity|source-summary|comparison), `created` (ISO date), `sources` (list)。读取时由 `scripts/fetch_doc.py` 的 `parse_frontmatter()` 解析;维护模式 lint 报告缺失。

### 6.7 Cross-References

`[[concept-name]]` 在**写入时**通过 `drive files list` 查找并渲染为飞书 doc 链接;找不到时保留字面量。读取时(qa)保持字面量,由 librarian 跟随引用(参考 `agents/librarian.md`)。

### 6.8 IM 接收人

所有 `im +messages-send` 发送至 `<IM_USER_ID>`。

### 6.9 删除 / 移动 / 重命名

**禁止**。所有标题必须在创建时正确,移动/删除/重命名都不允许。

## 7. Mode 1: qa (query)

最常用模式,默认。读 KB,回答用户问题。

### 7.1 入口

```
feishu-kb <question>   # 或 feishu-kb qa <question>
```

### 7.2 流程

```
1. Self-check (scripts/fetch_doc.py --self-check)
2. 多轮消解: 解析 "它"/"那"/"this paper" 指向 last_entities/last_concepts
3. 触发比较模式检测: "X vs Y" 且 ≥2 命中 entity doc → 提示 y/n,不自动创建
4. Spawn librarian (subagent_type=Explore, name="librarian", mode=qa)
5. librarian 跨 4-folder 搜索 → 抓取 → 引用跟随(5 层 + 循环检测)
6. 必要时触发 PDF parse (CrossRef + parse_pdf.py)
7. 主上下文合成回答 + 飞书链接
```

### 7.3 比较模式检测 (qa → maintain 副作用)

如果问题含 "X 和 Y 的区别" / "X vs Y" / "比较 X Y Z" 且 ≥2 个 term 命中 entity doc,主上下文提示:

> "检测到对比问题: X vs Y vs Z. 是否创建/更新 comparison 文档? (y/n)"

`y` → 切换到 maintain 模式(只读分析,经用户确认后写);`n` → 内联回答。**永不自动创建**。详见 `references/skill-activation.md`。

### 7.4 响应格式

```
## 回答

[内容,语言匹配用户提问]

---
**来源**:
- [doc 名](飞书链接)
- [doc 名](飞书链接)
```

论文必须附原文链接(DOI / CrossRef URL)。

### 7.5 写面 (qa 模式)

详见 `references/write-permissions.md` § qa。允许: `drive +upload` 到 PDF folder;`docs +update --mode append` 到当前抓取的 doc(用于追加 PDF 链接)。**禁止**: `docs +create`、移动/删除/重命名。

### 7.6 详细代理指令

`agents/librarian.md` § qa。

## 8. Mode 2: maintain (lint) — Stage 2 ACTIVE

执行知识库维护: dedup、lint、frontmatter 回填、KG 索引 scaffold、KB log 追加、IM 报告。

### 8.1 入口

```
feishu-kb 维护                    # 真实执行 (7 步全部跑完)
feishu-kb 维护 --dry-run          # 子 agent 跑分析,主上下文打印 JSON,跳过所有写操作
```

### 8.2 7 步流程

详细在 `references/maintain-flow.md`。摘要:

1. **读 KB state** + self-check (必须 `{"ok": true}`)
2. **强制 dedup** — `drive files list` 遍历 4 个 folder,报告同名重复
3. **Lint** — librarian (mode=maintain) + maintainer agent 分析: 矛盾/孤立/stale/重复/frontmatter 缺失
4. **KG table scaffold** — 只填空 KB index 中的空 section,不覆盖已有内容
5. **Frontmatter backfill** — `scripts/backfill_frontmatter.py --apply` (一次性,幂等)
6. **追加 KB log** — `docs +update --mode append` 到 `<KB_LOG_TOKEN>`
7. **IM 报告** — `im +messages-send` 到 `<IM_USER_ID>`

### 8.3 写面 (maintain 模式)

允许:
- `docs +create` 到 `<ENTITY_FOLDER_TOKEN>` (实体) / `<CONCEPT_FOLDER_TOKEN>` (概念) / `TBD_Stage1` (comparisons)
- `docs +update` 到 `<KB_INDEX_TOKEN>` (KB index) / `<KB_LOG_TOKEN>` (KB log)
- `docs +update --mode replace` 到任意 doc (backfill_frontmatter.py 的 frontmatter 回填)
- `im +messages-send` 到 `<IM_USER_ID>`

禁止: `docs +create` 到 论文 folder;`drive +upload`;删除/移动/重命名。

详见 `references/write-permissions.md` § maintain。

### 8.4 子 agent

- `librarian` (mode=maintain): 扫描 KB index + keyword lib,报告 orphan/stale 条目
- `maintainer`: 运行 lint,返回 JSON (`duplicates/lint/kg_table/log_entry/backfill_plan`)

所有写操作由主上下文执行,maintainer 不调用任何写命令。

## 9. Mode 3: update (ingest) — Stage 3 ACTIVE

执行论文检索: 4 源搜索 + RSS 轮询 + dedup + journal 过滤 + 创建论文摘要 doc。

### 9.1 入口

```
feishu-kb 检索 --query "mRNA LNP" --days 7
feishu-kb 检索 --query "..." --journal "Nature Biotechnology"
feishu-kb 检索 --query "..." --mock-source pubmed   # 测试用单源
```

### 9.2 7 步流程

详细在 `references/update-flow.md`。摘要:

1. **读 keyword lib** + self-check
2. **并行搜索** — `paper_search.py` (NCBI/CrossRef/Semantic/arXiv) + `rss_monitor.py`
3. **Dedup** — DOI exact → title-hash → priority merge
4. **Journal 过滤** — 目标期刊 (Nature/Science/Cell/顶会) + 排除列表
5. **并行摘要** — `paper-summarizer-v2` skill (旧 prompt 字面)
6. **CrossRef 验证** → `title_clean.py` → `docs +create` 到 `<PAPER_FOLDER_TOKEN>`
7. **更新 keyword lib** + **IM 报告** 到 `<IM_USER_ID>`

### 9.3 写面 (update 模式)

允许:
- `docs +create` 到 `<PAPER_FOLDER_TOKEN>` (论文 folder) only
- `docs +update --mode append` 到 `<KEYWORD_LIB_TOKEN>` (keyword lib)
- `im +messages-send` 到 `<IM_USER_ID>`

禁止: `docs +create` 到 实体/概念;`docs +update` 到 KB index/log;`drive +upload` (qa 拥有 PDF pipeline);删除/移动/重命名。

详见 `references/write-permissions.md` § update。

### 9.4 子 agent

- `librarian` (mode=qa, 历史查询扫描): 辅助历史查询
- `collector`: 运行 4 源搜索 + dedup + journal 过滤,返回 create-ready JSON (`papers[]`)

所有写操作由主上下文执行,collector 不调用任何写命令。

## 10. Shared Tokens

`references/search-scope.md` 是 canonical 来源;下表为摘要,token 变化时**先**改 `search-scope.md`,再同步其他文件。

| 用途 | Token |
|------|-------|
| 文献学习 (根) | <LIT_ROOT_TOKEN> |
| 论文 folder | <PAPER_FOLDER_TOKEN> |
| 实体 folder | <ENTITY_FOLDER_TOKEN> |
| 概念 folder | <CONCEPT_FOLDER_TOKEN> |
| PDFs folder | <PDF_FOLDER_TOKEN> |
| KB 索引 | <KB_INDEX_TOKEN> |
| KB log | <KB_LOG_TOKEN> |
| Keyword lib | <KEYWORD_LIB_TOKEN> |
| IM user | <IM_USER_ID> |
| 概念 cache: mRNA 序列设计 | <CACHE_MRNA_TOKEN> |
| 概念 cache: LNP 设计 | <CACHE_LNP_TOKEN> |
| 概念 cache: 基因编辑递送 | <CACHE_GENE_EDIT_TOKEN> |

## 11. Pre-Permissions (`~/.claude/settings.json`)

将以下条目加入 `~/.claude/settings.json` → `permissions.allow`（完整白名单见 `references/write-permissions.md`）:

```json
{
  "permissions": {
    "allow": [
      "Bash(npx @larksuite/cli drive files list*)",
      "Bash(npx @larksuite/cli drive files get*)",
      "Bash(npx @larksuite/cli drive +upload*)",
      "Bash(npx @larksuite/cli docs +fetch*)",
      "Bash(npx @larksuite/cli docs +create*)",
      "Bash(npx @larksuite/cli docs +update*)",
      "Bash(npx @larksuite/cli im +messages-send*)",
      "Bash(curl -s -A *https://api.crossref.org*)",
      "Bash(curl -s -A *https://eutils.ncbi.nlm.nih.gov*)",
      "Bash(curl -s *api.semanticscholar.org*)",
      "Bash(curl -s *export.arxiv.org*)",
      "Bash(wget *nature.com*)",
      "Bash(wget *science.org*)",
      "Bash(wget *cell.com*)",
      "Bash(wget *biorxiv.org*)",
      "Bash(jq *)",
      "Bash(conda run -n marker python /path/to/scripts/parse_pdf.py*)",
      "Bash(conda run -n marker python /path/to/scripts/fetch_doc.py*)",
      "Bash(conda run -n marker python /path/to/scripts/crossref_lookup.py*)",
      "Bash(conda run -n marker python /path/to/scripts/title_clean.py*)",
      "Bash(conda run -n marker python /path/to/scripts/backfill_frontmatter.py*)",
      "Bash(conda run -n marker python /path/to/scripts/paper_search.py*)",
      "Bash(conda run -n marker python /path/to/scripts/rss_monitor.py*)",
      "Bash(mkdir -p /tmp/feishu-kb-*)",
      "Bash(mkdir -p ~/.cache/feishu-kb*)",
      "Agent",
      "Read",
      "Write",
      "Edit"
    ]
  }
}
```

**注意**: 将 `/path/to/scripts/` 替换为实际安装路径。完整白名单和说明见 `references/write-permissions.md`。


## 12. Error Handling

| 失败 | 处理 |
|------|------|
| Self-check 失败 | halt,提示 "KB root token stale. Update references/search-scope.md" |
| 知识库无结果 | qa: "知识库中未找到相关信息";update: 跳过该 query,继续下一个 |
| 文档获取失败 (fetch) | 跳过该 doc,继续其他结果 |
| PDF 下载失败 | 退化为只用 docx + CrossRef abstract,提示用户 |
| 写入失败 (create / update) | halt,保留子 agent 输出,提示用户重试 |
| 4-folder 范围外 token | 拒绝调用,提示 "scope violation" |
| 比较模式自动触发 | 永不发生;只 prompt 用户 |

## 13. Tests

`tests/` 目录下分阶段测试:

- `tests/test_qa_mode.md` — 6 个 qa 测试 (stage 1)
- `tests/test_maintain_mode.md` — 2+ 个 maintain 测试 (stage 2)
- `tests/test_update_mode.md` — 3+ 个 update 测试 (stage 3)
- `tests/test_integration.md` — 跨模式集成测试 (stage 2/3)

每个 stage 实现后跑对应测试,全部通过才进入下一 stage。

## 14. Cross-References

| 文件 | 用途 |
|------|------|
| `references/skill-activation.md` | 触发表 + 路由优先级 + 多轮上下文 + 比较模式检测 |
| `references/search-scope.md` | **Canonical token 表**;所有 token 改这里 |
| `references/write-permissions.md` | 每模式 lark-cli 白名单 (全部激活) |
| `references/crossref-helper.md` | DOI/title → metadata + abstract 流程 |
| `references/wiki-schema.md` | **Karpathy 对齐** frontmatter + page templates + naming |
| `references/title-format.md` | paper doc 命名格式 `{FirstAuthor}_{Year}_{CleanedTitle}` |
| `references/maintain-flow.md` | 7 步维护流程 |
| `references/update-flow.md` | 7 步检索流程 |
| `references/paper-search.md` | 4 源 curl 模板 |
| `references/dedup-strategy.md` | DOI + title-hash + priority merge |
| `references/rss-feeds.md` | 高影响期刊 RSS 列表 |
| `agents/librarian.md` | KB 检索 + 引用跟随;`mode=qa` (默认) / `mode=maintain` |
| `agents/maintainer.md` | 维护分析(只读,返回 JSON) |
| `agents/collector.md` | 检索分析(只读,返回 JSON) |
| `scripts/fetch_doc.py` | 5 层引用跟随 + self_check + parse_frontmatter |
| `scripts/parse_pdf.py` | qa 模式的 PDF 解析 (marker env) |
| `scripts/crossref_lookup.py` | CrossRef API 客户端 |
| `scripts/title_clean.py` | 标题清洗 + 文件名生成 |
| `scripts/paper_search.py` | 4 源聚合器 |
| `scripts/rss_monitor.py` | RSS poller |
| `scripts/backfill_frontmatter.py` | 一次性 frontmatter 回填 |

## 15. Versioning & Changelog

- **v1.0.0** (stage 1+2+3): 三模式整合完成;旧 `feishu-kb-maintain` / `feishu-kb-update` 删除;frontmatter 已回填。
- **v1.1.0** (future): `feishu-kb --init` 走 drive 重新生成 `search-scope.md`;KG 自动模式 (after scaffold 运行几次后);`comparisons/` 文件夹自动建议。

变更原则: 任何 token 改动**先**改 `references/search-scope.md`,再同步;任何写面改动**先**改 `references/write-permissions.md`,再同步 SKILL.md 和 agent prompt。
