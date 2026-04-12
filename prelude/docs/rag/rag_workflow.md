# RAG Workflow（实现对齐版）

本文档只描述当前代码的真实行为与约束，不做概念性扩展。

## 1. 目标与边界

目标：从文档站点构建可检索的向量索引。

处理链路：

`crawl -> parse -> chunk -> embed -> store`

当前实现入口：

- `prelude/scripts/build_index.py`

## 2. 配置来源

### 2.1 站点配置

- 文件：`prelude/config/craw_list.yaml`
- 作用：定义站点列表、是否启用、每站 `max_page` 可选覆盖。

### 2.2 管线默认参数

- 文件：`prelude/config/rag_pipeline.yaml`
- 当前关键默认值：
  - `crawl.default_max_page: 200`
  - `chunking.max_tokens_per_chunk: 1024`
  - `embedding.model: BAAI/bge-m3`
  - `embedding.batch_size: 2`
  - `embedding.max_seq_length: 1024`

参数读取：`prelude/rag/pipeline_config.py`

## 3. Phase 1 - Crawl

实现：`prelude/rag/crawlers/gitbook_crawler.py`

行为：

1. 从 `base_url` 出发，BFS 方式抓取页面。
2. 导航策略：
   - 先 `wait_until=networkidle, timeout=30000`
   - 超时后降级 `wait_until=domcontentloaded, timeout=45000`，并额外等待 1200ms
3. 链接提取：仅保留同站链接（`startswith(base_url)`），忽略 `#anchor`。
4. 每页保存原始 HTML 到 `prelude/data/raw_html/<site>/`。

`build_index.py` 会优先使用本地 `raw_html` 缓存；`--rebuild` 从指定 stage 起清理并重建。

## 4. Phase 2 - Parse

### 4.1 HTML -> Markdown 预清洗

实现：`prelude/rag/parsers/html_to_markdown.py`

当前流程：

1. 提取正文容器（优先）：
   - `<main>` 下直接子节点 `header + div.whitespace-pre-wrap`
   - 回退：`main` 整体
   - 再回退：`article` / `[role='main']` / `.content` / `#content` / `body`
2. 移除 UI 噪声节点：`nav/footer/aside/button/svg/...` 与部分 GitBook `data-testid` 节点。
3. 将 `role="table"` 的 ARIA 表格归一化为真实 `<table>`。
4. 调用 `markdownify` 转 Markdown。
5. 行级清洗：
   - 裁掉首个 heading 前的噪声
   - 删除常见 UI 噪声行（如 `Last updated...`、`Powered by GitBook`、`copy...`）

### 4.2 Markdown -> MarkdownBlock

实现：`prelude/rag/parsers/markdown_parser.py`

当前解析行为（按行扫描）：

1. `#`~`######` 作为 heading，同时会生成一个 `block_type="text"` 的标题块。
2. 代码围栏 ```...``` 生成 `block_type="code"`。
3. Markdown 表格（含分隔线）生成 `block_type="table"`。
4. 有序/无序列表分别生成 `ordered_list` / `unordered_list`。
5. 普通段落生成 `text`。

注意：

- `MAX_NESTING_DEPTH` 常量存在，但当前列表解析不是完整递归 AST；有序列表下的嵌套无序项会被拼成字符串。
- `parsed_blocks` 会写入 `prelude/data/parsed_blocks.jsonl`。

## 5. Phase 3 - Chunk

实现：`prelude/rag/chunkers/semantic_chunker.py`

### 5.1 token 估算

当前顺序：

1. 优先使用 embedding 模型对应 tokenizer（BGE-M3，本地 snapshot 优先）
2. 回退 `tiktoken(cl100k_base)`
3. 最后回退 `chars/4`

### 5.2 分组与切分

当前分组键：`heading_path`（tuple）。

注意：分组键当前不含 `source_url`，理论上可能出现跨页面同标题分组。现网样本中已观察到少量此类键冲突风险。

处理流程：

1. 空 heading 保护：如果该组是空 heading 且含多个 block，不做整组合并，而是逐 block 处理（防止噪声大块）。
2. 组内按类型分流：
   - `table`、`code`：每个 block 单独成 chunk（当前不做 token 上限切分）
   - `text/ordered_list/unordered_list`：先合并为一个 `text` chunk，再按 `max_tokens_per_chunk` 判断
3. 超限 `text` 切分：
   - 先按 block 预算切
   - 单 block 过大时按段落/行再切
   - 仍过大按空白分词切
   - 极端长词回退为固定窗口（256 chars）

输出：`prelude/data/chunks.jsonl`

### 5.3 flatten 规则（用于 embedding 文本）

实现：`block_to_embedding_text` + `flatten_block`

- `heading_path` 会作为前缀：`[H1 > H2 > ...]`
- `table` 当前只展开表头 + 前 3 行 + 剩余行计数（不是全表逐行展开）

## 6. Phase 4 - Embedding + Storage

实现：`prelude/rag/embedders/embedding_pipeline.py`

行为：

1. 模型加载：本地 HF snapshot 优先，失败再用 model id 远程加载。
2. 设置 `self.model.max_seq_length`（来自配置，当前 1024）。
3. 按 `batch_size` 调用 `SentenceTransformer.encode`。
4. 存入 Chroma PersistentClient（`prelude/data/vectorstore`）。

## 7. 调查与验收脚本

### 7.1 通用统计（单一职责）

- `prelude/scripts/analyze_chunks.py`
- 功能：token 分布、阈值计数、最长样本 TopN

### 7.2 事故调查（问题导向）

- `prelude/scripts/investigate_chunk_outliers.py`
- 功能：按 `batch/head/dtype/memory` 估算风险阈值，定位高风险 chunk，回溯候选 block

## 8. 当前状态（基于最近一次修复后复测）

复测口径：在现有 `raw_html` 缓存上重新 parse+chunk。

- 已修复关键问题：
  - 正文抽取 + UI 噪声剔除
  - ARIA table 归一化
  - 空 heading 聚合保护
  - token 估算与 embedding tokenizer 对齐
- 当前分布：
  - `>2048` 为 0
  - `>1024` 仅少量（最新一次为 1 个）
  - `max` 约 1429

## 9. 已知限制（与后续改进方向）

1. 分组 key 未包含 `source_url`，建议改为 `(source_url, heading_path)`。
2. `table/code` 目前不受 token 上限切分，需按业务策略补“保留完整优先 + 安全上限”。
3. 列表解析不是完整递归结构；如需更强结构语义，需重构 parser。
4. `flatten_table` 仅前 3 行摘要，若检索依赖深行内容，需改为可配置行数或全表策略。

## 10. 常用命令

在 `prelude/` 下：

```bash
# 全量重建
uv run python scripts/build_index.py --rebuild

# 从 chunk 阶段重建
uv run python scripts/build_index.py --from-stage chunk --rebuild

# chunk 分布统计
uv run python scripts/analyze_chunks.py --chunks data/chunks.jsonl --top-n 20
```
