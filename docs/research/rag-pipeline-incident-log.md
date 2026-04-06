# RAG 管线事故记录（RAG Pipeline Incident Log）

## 2026-04-06 - BGE-m3 在超大分块（oversized chunks）上的 OOM

### 现象（Symptom）

`build_index.py` 在 `crawl / parse / chunk` 阶段完成后，在 `embedding` 阶段失败：

```text
RuntimeError: Invalid buffer size: 62.38 GiB
```

报错位置在 `sentence_transformers / transformers` 的注意力前向计算（attention forward）路径：

- `prelude/rag/embedders/embedding_pipeline.py`
- `self.model.encode(texts, **self.encode_kwargs)`

### 上下文（Context）

- 嵌入模型（Embedding model）：`BAAI/bge-m3`
- 语料中包含较长页面（例如条款、规格、较大表格）
- `chunks` 产物中存在超大分块（字符级观测最大约 `19k+`）

### 工作假设（Working hypothesis）

这是由长序列注意力开销（long-sequence attention cost）与批处理编码（batch encoding）共同触发的内存压力问题。实际表现为：部分 chunk 过大，导致 `bge-m3` 在当前机器设置下无法稳定完成编码。

面向初学者的内存估算与推导说明见：
`docs/research/bge-m3-attention-memory-estimation.md`

### 立即观察（Immediate notes）

- 该问题与爬取稳定性（crawl stability）是独立问题。
- 后续可验证的缓解方向：
  1. 对所有块类型（含 table/code）加统一硬上限（hard max chunk size）
  2. 下调 embedding `batch_size`
  3. 编码时设置 `max_seq_length` 并做截断（truncate）
  4. 在 chunking 前过滤低价值重复页（如 revision 镜像页）

### 复现状态（Reproduction status）

- 已在真实运行中复现：`crawl -> parse -> chunk` 成功后，`Step 4 embedding` 失败。
- 在当前数据分布下，失败可稳定出现。

### 调查工具拆分（Tooling split）

为了让分析方法可复用，工具按职责拆分为两类：

1. 通用统计工具（保持单一职责）  
   `prelude/scripts/analyze_chunks.py`
   - 只做分布统计：分位数、阈值计数、最长样本 TopN
   - 不绑定任何具体事故

2. 事故调查工具（问题导向）  
   `prelude/scripts/investigate_chunk_outliers.py`
   - 用给定 `batch/head/dtype/memory` 反推风险长度阈值 $L$
   - 标记潜在 OOM chunk
   - 回溯到 `parsed_blocks.jsonl`，定位 `source_url + heading_path` 对应的上游块

### 可复用调查流程（Reusable procedure）

在 `prelude/` 目录执行：

```bash
# 1) 通用分布盘点
uv run python scripts/analyze_chunks.py \
  --chunks data/chunks.jsonl \
  --threshold 512 --threshold 1024 --threshold 2048 --threshold 4096 \
  --top-n 20 \
  --json-out data/reports/chunk_token_distribution.json

# 2) 复盘 OOM 场景（batch=32）
uv run python scripts/investigate_chunk_outliers.py \
  --chunks data/chunks.jsonl \
  --parsed-blocks data/parsed_blocks.jsonl \
  --batch-size 32 --heads 16 --dtype-bytes 4 --memory-gib 8 \
  --top-n 20 \
  --json-out data/reports/chunk_outlier_investigation_b32_m8.json

# 3) 当前配置对照（batch=2）
uv run python scripts/investigate_chunk_outliers.py \
  --chunks data/chunks.jsonl \
  --parsed-blocks data/parsed_blocks.jsonl \
  --batch-size 2 --heads 16 --dtype-bytes 4 --memory-gib 8 \
  --top-n 20 \
  --json-out data/reports/chunk_outlier_investigation_b2_m8.json
```

### 本次调查结果（2026-04-06）

#### A. 分布结论

- chunk 总数：`599`
- token 分布（BGE-M3 tokenizer）：`p50=335, p90=4428, p95=4763, p99=5103, max=5719`
- 超阈值计数：
  - `>1024`: `110`
  - `>2048`: `83`
  - `>4096`: `66`

#### B. OOM 预算对照

- 假设：`B=32, H=16, dtype=float32(4 bytes), memory=8 GiB`
- 反推阈值：`L≈2048`
- 实测超过该阈值 chunk 数：`83`
- 最大 chunk（`L=5719`）对应 attention buffer 约 `62.38 GiB`，与报错一致。

#### C. 上游回溯信号

- 典型大 chunk 可映射回大量上游块：
  - `https://docs.lighter.xyz/trading/trading-fees`：同组 `110` 个 text blocks
  - `https://docs.lighter.xyz/trading/contract-specifications`：同组 `701` 个 text blocks
- 大量超长 chunk 具有：
  - `heading_path` 为空（`empty_heading_count=58`）
  - 导航/目录噪声特征（`nav_like_count=178`，如 `chevron-right`, `Powered by GitBook`）
- token 估算偏差（`model_vs_estimator_ratio`）在 Top outliers 中约 `1.17 ~ 1.40`。

### 根因归纳（Root cause）

1. chunk 分组粒度在部分页面上过粗，导致单组聚合过多 block。  
2. 上游 Markdown 中混入导航与模板噪声，放大了“空 heading 组”的体积。  
3. token 预算控制与实际模型 tokenizer 不完全一致，导致“估算安全、实际过长”的风险。  
4. table/code 的超长保护需要与 text 一样采用统一硬上限策略（避免绕过预算）。

### 处置与固化（Resolution and hardening）

1. embedding 默认参数收敛到低风险配置：`batch_size=2`, `max_seq_length=1024`。  
2. chunk 目标参数固定到可控范围：`target=512`, `max=1024`, `overlap=96`。  
3. 将上述调查流程固化为脚本，便于后续在不同语料集重复执行。  
4. 后续继续推进：
   - 在 parse/chunk 前增加导航噪声过滤
   - 对空 heading 大组增加保护性拆分规则
   - 用模型 tokenizer 校准 chunk token 预算

### 2026-04-06 补充：首轮 bug 修复后的快速复测

本轮已落地的“真实 bug 修复”：

1. `HTML -> Markdown` 前先提取正文区域（`main` 的 `header + div.whitespace-pre-wrap`），避免整页导航进入解析。  
2. 将 `role=table` 的 ARIA 表格标准化为 `<table>`，再交给 markdownify。  
3. chunker 对空 `heading_path` 组加保护：不再把同页所有 orphan blocks 聚合成单个大 chunk。

在现有 `raw_html` 缓存上做 parse+chunk 复测（不含 embedding）结果：

- 解析块总量：`9167 -> 2491`
- `table` block：`0 -> 34`
- 空 `heading_path` blocks：`0`（此前存在大量空路径噪声块）
- chunk token 最大值（BGE-M3 tokenizer）：`5719 -> 1429`
- `>2048` token chunk：`83 -> 0`
- `>4096` token chunk：`66 -> 0`

说明：OOM 主因（导航噪声 + 过粗聚合 + 表格识别缺失）已被显著抑制。  
剩余 `>1024` 的 chunk 仍有少量（约 25），主要是正文长段落，可在下一轮通过更严格 token 预算切分继续收敛。

### 2026-04-06 补充（二）：token 估算器对齐后

将 chunker 的 token 估算从 `tiktoken(cl100k)` 切换为 BGE-M3 tokenizer（本地 snapshot 优先）后，再次复测：

- chunk 总数：`637`
- token 分布：`p50=180, p90=720, p95=883, p99=986, max=1429`
- `>1024`：仅 `1` 个
- `>2048`：`0`
- 该 `>1024` 样本类型为 `text`，来源：`https://docs.variational.io/omni/getting-started-with-omni`

结论：当前超阈值问题已基本收敛，不再由表格主导。
