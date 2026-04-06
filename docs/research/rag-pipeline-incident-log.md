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
