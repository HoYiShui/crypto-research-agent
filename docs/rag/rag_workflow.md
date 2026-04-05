# RAG 完整流程详解

> 基于 Hyperliquid GitBook Docs 的真实案例

## 流程总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                     索引构建阶段（离线）                              │
│  Crawling ──→ Parsing ──→ Chunking ──→ Embedding ──→ Storage       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     检索阶段（在线）                                  │
│                                                                     │
│  User Query ──→ Embed ──→ Vector DB ──→ Top-k Chunks               │
│                                    │                                │
│                                    ├── Vector Search（HNSW 索引）    │
│                                    └── Metadata（原始文本）           │
│                                                                     │
│                                     Rerank ──→ Prompt ──→ LLM ──→ Answer
└─────────────────────────────────────────────────────────────────────┘
```

**索引构建阶段**（离线，一次性）：数据采集 → 解析 → 切分 → 向量化 → 存入 Vector DB

**检索阶段**（在线，每次查询）：Query 向量化 → Vector DB 搜索 → Rerank → Prompt 组装 → LLM 生成

**Vector DB 不是分支，而是数据源**：存储阶段把 chunks 的向量存入 Vector DB，检索阶段从 Vector DB 查询。Vector Search 是操作，Vector DB 是被操作的对象。

---

## Phase 1: 数据采集（Crawling）

**目标**：把整个站点拉下来，保留页面结构和原始内容

```
GitBook: https://hyperliquid.gitbook.io/hyperliquid-docs
    │
    ├── 递归抓取所有子页面（从首页开始）
    ├── 识别站点地图（GitBook 通常有 /sitemap.xml）
    └── 存储原始 HTML + URL + 抓取时间
```

**工具**：Playwright（JS 渲染）+ BeautifulSoup（HTML 解析）

---

## Phase 2: 数据解析（Parsing）

**目标**：把 Markdown（或 HTML 转化的 Markdown）转成带层级标记的结构化 Block 对象

**核心洞察**：
> **Parsing 的关键在于保留完整的语法结构。** Markdown 语法本身已经定义了语义结构（标题级别、有序/无序列表、缩进），解析器应该完整保留这些结构，而不是"推测意图后合并"。

**长板趋势**：处理器性能不断提高，嵌套解析的性能消耗可以忽略不计。

**Tradeoff**：嵌套深度越深，递归处理越复杂。但真实文档嵌套深度几乎不超过 2 层，可以直接递归处理而不设硬性上限。

**核心原则**：Parsing 只做结构识别，不做内容改写。

### 关键洞察：语法结构 = 语义结构

文档的语法结构和语义结构越一致，Chunking 越简单、向量质量越高。

```
Markdown 天生具有这个特性：
- H1/H2/H3 本身就是语义层级
- 有序/无序列表本身就是语义分组
- 表格本身就是结构化语义单元

这些 block 类型：
- 语法边界 = 语义边界
- 语法长度 ≈ 语义长度
- 所以按语法切就够了，不需要额外判断
```

### 数据结构设计

```python
from dataclasses import dataclass
from typing import Union

@dataclass
class MarkdownBlock:
    """解析阶段的输出单元"""
    block_id: str
    heading_path: list[str]      # 当前 block 所属的标题路径，如 ["Fees", "Maker rebates"]
    heading_level: int          # 标题级别：1=H1, 2=H2, 3=H3...
    block_type: str             # "text" | "ordered_list" | "unordered_list" | "table" | "code"

    # 对于 text 块
    content: str | None = None

    # 对于 ordered_list / unordered_list
    # items 可能是字符串（简单列表项）或 MarkdownBlock（有嵌套结构的列表项）
    items: list[Union[str, "MarkdownBlock"]] | None = None

    # 对于 table 块
    table_headers: list[str] | None = None
    table_rows: list[list[str]] | None = None

    # 对于 code 块
    code: str | None = None
    code_lang: str | None = None
```

### 解析示例：Fees 页面

```
原始 Markdown:
## Fees
Fees are based on your rolling 14 day volume...
## Perps fee tiers
| Tier | 14d vol | Taker | Maker | ...
解析结果:
MarkdownBlock(block_id="b1", heading_path=["Fees"], heading_level=2,
             block_type="text", content="Fees are based on your rolling 14 day volume...")
MarkdownBlock(block_id="b2", heading_path=["Fees", "Perps fee tiers"], heading_level=2,
             block_type="table", table_headers=["Tier", "14d vol", ...],
             table_rows=[["0", "0", "0.045%", "0.015%"], ...])
```

### 解析示例：嵌套列表

```markdown
## What do I need to trade on Hyperliquid?

If you choose to use a normal defi wallet, you need:

1. An EVM wallet
   - If you don't already have an EVM wallet (e.g., Rabby, MetaMask...)...
   - After downloading a wallet extension for your browser...
   - Your wallet has a secret recovery phrase...

2. Collateral
   - USDC and ETH on Arbitrum, or
   - BTC on Bitcoin...
```

解析结果：

```python
MarkdownBlock(
    block_id="b1",
    heading_path=["What do I need to trade on Hyperliquid?"],
    heading_level=2,
    block_type="ordered_list",
    items=[
        # Item 1：嵌套了无序列表
        MarkdownBlock(
            block_id="b1_1",
            block_type="text",
            content="An EVM wallet",
            items=[
                MarkdownBlock(
                    block_id="b1_1_nested",
                    block_type="unordered_list",
                    items=[
                        "If you don't already have an EVM wallet (e.g., Rabby, MetaMask...)...",
                        "After downloading a wallet extension for your browser...",
                        "Your wallet has a secret recovery phrase..."
                    ]
                )
            ]
        ),
        # Item 2：同样嵌套
        MarkdownBlock(
            block_id="b1_2",
            block_type="text",
            content="Collateral",
            items=[
                MarkdownBlock(
                    block_id="b1_2_nested",
                    block_type="unordered_list",
                    items=[
                        "USDC and ETH on Arbitrum, or",
                        "BTC on Bitcoin...",
                        "ETH/ENA on Ethereum...",
                    ]
                )
            ]
        )
    ]
)
```

### 嵌套层级处理

**原则**：真实文档嵌套深度几乎不超过 2 层。设上限 `MAX_NESTING_DEPTH = 3`，超过则打平。

```python
MAX_NESTING_DEPTH = 3

def parse_nested(node, depth=0):
    if depth >= MAX_NESTING_DEPTH:
        return flatten_to_string(node)  # 打平为字符串
    # 正常递归解析...
```

### Parsing vs Chunking 的清晰分工

```
Parsing（按语法结构切）：
  Markdown → list[MarkdownBlock]
  输入: Markdown 字符串
  输出: 带 heading_path 的 blocks
  规则: 遇到 H2/H3 开新 block；遇到有序/无序列表继续递归解析嵌套
  原则: 不做 token 估算，不做合并改写

Chunking（按语义 + 字数切）：
  list[MarkdownBlock] → list[Chunk]
  输入: 带 heading_path 的 blocks
  输出: 准备 embedding 的 chunks
  规则:
    1. 按 heading_path 聚合（同一 H2 下的 blocks 合并）
    2. 检查 token 量，超限则按子标题再切
    3. 表格不切（整表一个 chunk）
```

### 解析要点

- **表格**：保留行列结构，不打散成文本
- **代码块**：单独 block，标记语言类型
- **嵌套列表**：继续递归解析，不打平成字符串
- **侧边栏导航**：不进 Document，作为 page-level metadata
- **Embedding 时**：通过 `flatten_block()` 把递归结构展平为线性文本（见 Chunking 部分）

---

## Phase 3: 文档切分（Chunking）

**目标**：把 list[MarkdownBlock] 变成 list[Chunk]，每个 Chunk 准备做 embedding

**核心洞察**：
> **Chunking 的关键在于划分出区分度高的语义结构，以提高检索命中率。** 但长板趋势是模型能力不断提高，倾向于通过大 chunk 给模型暴露更多 context，以提高生成质量。

**核心原则**：语义连贯的大单元优先用大 chunk，不强行切；语义独立的小单元保持独立，不强制合并。Chunking 的目标不是"完美的语义切分"，而是"最大化模型对语义的理解"。

### 关键洞察：大 Chunk 优于多个小 Chunk

```
传统观点：
  小 chunk = 精确，检索命中率高
  大 chunk = 嘈杂，信息密度低

新观点（基于模型能力趋势）：
  模型能力不断增强：
  - Claude 3.5: 200K context
  - GPT-4o: 128K context
  - Gemini 1.5: 1M context

  大 chunk = 更多 context = 模型理解更深 = 比多个小 chunk 更好
  切小 = embedding 各自为政，语义分散 = top-N 召回数个 chunks = 暴露信息量反而减少
```

### Table 和 Ordered_list 的特殊性

```
Table 和 Ordered_list 类型的 block：
- 语法结构 = 语义结构（天然一致）
- context 十分强力
- 因此不需要按 token 量来 chunk
- 即使 token 量再大，直接使用大 chunk 即可

对比 Text 类型 block：
- 语法结构 ≠ 语义结构（段落可能讲多件事）
- 需要按 heading_path 聚合后检查 token 量
```

### Chunk size 差异是否影响 embedding 质量？

```
结论：chunk size 差异本身不是问题，semantic coherence 才是。

Embedding 模型无论输入是 10 tokens 还是 2000 tokens：
→ 输出都是固定维度的向量（如 1536 维）
→ 向量维度固定不变

真正影响 embedding 质量的是：
- Semantic coherence：chunk 讲一件事，比讲多件事的向量更"纯粹"
- Context completeness：完整段落比残缺片段的向量更有意义

刻意追求 chunk size 一致是迷思。
```

### Chunking 流程

```
Step 1: 按 heading_path 聚合
        同一个 heading 下的所有 MarkdownBlock 合并成一组

Step 2: 检查 token 量（但大 chunk 优先）
        合并后 ≤ 2048 tokens → 一个 Chunk（语义连贯优先）
        合并后 2048 ~ 4096 tokens → 可接受（model 能 handle）
        合并后 > 4096 tokens → 找子标题再切（语义可能不纯粹）

Step 3: 生成 chunk 对象
        text 类型 block → 调用 flatten_block() 转文本
        table 类型 block → 整表保留（不检查 token）
        ordered_list 类型 block → 展平为带编号的描述文本（不检查 token）
```

### flatten_block()：把递归结构展平为 embedding 文本

```python
def flatten_block(block: MarkdownBlock, depth: int = 0) -> str:
    """把 MarkdownBlock 展平为线性文本，供 embedding 使用"""
    indent = "  " * depth

    if block.block_type == "text":
        lines = block.content.split('\n')
        return "\n".join(f"{indent}{line}" for line in lines)

    elif block.block_type == "unordered_list":
        lines = []
        for item in (block.items or []):
            if isinstance(item, str):
                lines.append(f"{indent}- {item}")
            else:
                lines.append(flatten_block(item, depth + 1))
        return "\n".join(lines)

    elif block.block_type == "ordered_list":
        lines = []
        for i, item in enumerate(block.items or [], 1):
            if isinstance(item, str):
                lines.append(f"{indent}{i}. {item}")
            else:
                lines.append(flatten_block(item, depth))
        return "\n".join(lines)

    elif block.block_type == "table":
        # 生成表格的结构化描述文本（不是原始行列数据）
        lines = [
            f"{indent}Table: {', '.join(block.table_headers or [])}",
        ]
        for row in (block.table_rows or [])[:3]:  # 只取前3行作为示例
            lines.append(f"{indent}  Row: {', '.join(str(c) for c in row)}")
        if len(block.table_rows or []) > 3:
            lines.append(f"{indent}  ... and {len(block.table_rows) - 3} more rows")
        return "\n".join(lines)

    elif block.block_type == "code":
        return f"{indent}Code ({block.code_lang}):\n{indent}{block.code}"

    return ""


def block_to_embedding_text(block: MarkdownBlock) -> str:
    """生成用于 embedding 的文本"""
    heading = " > ".join(block.heading_path)
    body = flatten_block(block)
    return f"[{heading}]\n{body}"
```

### Fees 页面 Chunking 结果

```
输入: list[MarkdownBlock]（来自 Parsing）

Step 1: 按 heading_path 聚合
  ["Fees"] 下的 text block → Group 1
  ["Fees", "Perps fee tiers"] 下的 table block → Group 2
  ["Fees", "Spot fee tiers"] 下的 table block → Group 3
  ...以此类推

Step 2: 检查 token 量
  Group 1 (~300 tokens) < 1024 → Chunk 1
  Group 2 (表格) → Chunk 2（整表，不检查字数）
  Group 3 (表格) → Chunk 3
  ...以此类推

输出:
├── Chunk 1 (text, ~300 tokens): [Fees] 费用说明段落
├── Chunk 2 (table): perps_fee_tiers（整表存入）
├── Chunk 3 (table): spot_fee_tiers
├── Chunk 4 (table): staking_tiers
├── Chunk 5 (table): maker_rebates
├── Chunk 6 (text, ~150 tokens): [Fees/Maker rebates] maker rebate 说明
├── Chunk 7 (code): typescript feeRates() 完整函数
└── Chunk 8 (text, ~200 tokens): [Fees/Staking linking] Staking linking 说明
```

### 嵌套列表的 Chunking

```markdown
1. An EVM wallet
   - If you don't already have an EVM wallet...
   - After downloading a wallet extension...
   - Your wallet has a secret recovery phrase...

2. Collateral
   - USDC and ETH on Arbitrum, or
   - BTC on Bitcoin...
```

```
整个 ordered_list block (~300 tokens) < 1024
→ 一个 Chunk，不切

Embedding 文本：
"""
[What do I need to trade on Hyperliquid?]
1. An EVM wallet
   - If you don't already have an EVM wallet (e.g., Rabby, MetaMask...)
   - After downloading a wallet extension for your browser...
   - Your wallet has a secret recovery phrase...

2. Collateral
   - USDC and ETH on Arbitrum, or
   - BTC on Bitcoin, ETH/ENA on Ethereum, SOL/... on Solana...
"""
```

如果 token 超限（罕见）：
```
→ 按 list_item 切成 sub-chunks
  Chunk 1: "1. An EVM wallet\n  - ...\n  - ..."
  Chunk 2: "2. Collateral\n  - USDC...\n  - BTC..."
  每个 sub-chunk 保留编号作为上下文
```

### Chunk metadata

```python
@dataclass
class Chunk:
    chunk_id: str
    source_url: str                    # 来源页面 URL
    heading_path: list[str]           # 导航路径，如 ["Trading", "Fees"]
    chunk_type: str                   # "text" | "table" | "code" | "ordered_list"
    heading_level: int               # 所属标题级别
    token_count: int                 # token 数量（用于分析）
    content_for_embedding: str        # flatten_block() 生成的文本
    raw_block: MarkdownBlock         # 原始 block（保留结构信息）
```

### 切分策略总结

| 内容类型 | 切分策略 | 理由 |
|---------|---------|------|
| 段落文本 | 按 heading 聚合后检查 token（> 4096 才切）| 语义连贯优先，大 chunk 给 model 更多 context |
| 有序/无序列表 | **不按 token 量切**，直接作为 semantic unit | 语法结构 = 语义结构，编号关系本身是语义 |
| 表格 | **不按 token 量切**，整表作为 semantic unit | 行列关系是数据本身，切了就没了 |
| 代码块 | **不按 token 量切**，整个函数作为 semantic unit | 函数是独立语义单元 |
| 嵌套结构 | 展平为线性文本，保留缩进层级 | embedding 需要线性输入 |

---

## Phase 4: Embedding

**目标**：把 Chunk 的文本转成向量，用于相似度检索

**Embedding 策略**：

| 内容类型 | Embedding 方法 | 原理 |
|---------|---------------|------|
| 普通文本 | 直接 encode | Transformer 上下文压缩 |
| 表格 | 转成 "Row X: col1, col2..." 文本 | 模型把表格格式学进了预训练 |
| 代码 | 直接 encode 或加语言提示 | 代码在预训练数据中，模型能理解 |
| 嵌套列表 | flatten_block() 后 encode | 同普通文本 |

**核心原理**：

```
输入文本 → Tokenizer → Token IDs → Transformer Encoder → Output Vector

Embedding 模型本质上是一个"上下文感知的语义特征提取器"：
- 输入是什么不重要（文本/表格/代码）
- 重要的是：转成 token 序列 → Transformer 处理上下文 → 输出语义向量
```

**表格的 embedding 方法**：

```python
# 由 flatten_block() 自动生成：
"""
[Fees > Perps fee tiers]
Table: Tier, 14d weighted volume ($), Taker, Maker
  Row: 0, 0, 0.045%, 0.015%
  Row: 1, >5M, 0.040%, 0.012%
  Row: 2, >25M, 0.035%, 0.008%
  Row: 3, >100M, 0.030%, 0.004%
  ... and 4 more rows
"""
```

**工具选择**：
- Embedding 模型：`text-embedding-3-small`（OpenAI）或 `bge-m3`（开源本地）
- 业界常用：OpenAI ada/BGE-m3/Cohere embed-v3

---

## Phase 5: 存储（Storage）

**目标**：把向量 + 元数据存入 Vector DB，供后续检索

**Vector DB 存两样东西**：

```
1. 向量 (Vector)
   - 搜索引擎的核心，用于相似度检索

2. 元数据 + 原始文本 (Metadata + Raw Chunk)
   - chunk 的 heading_path、source_url、block_type 等
   - 原始 content_for_embedding 文本
   - 用于 Retrieval 后组装 Prompt
```

**为什么原始文本也要存**：

```
检索过程：
  Query → 找到 top-k vectors → 拿到 chunk_ids → 读取原始文本 → 组装 Prompt

Vector DB 返回的是：
  chunk_id, similarity_score, vector

但 Prompt 组装需要的是：
  chunk 的原始文本内容（heading_path + content_for_embedding）
```

**实际存储结构**：

```python
# 伪代码：存储一个 chunk
from chroma import Chroma

db = Chroma(persist_directory="./chroma_db")

chunk = {
    "chunk_id": "chunk_001",
    "heading_path": ["Fees", "Perps fee tiers"],
    "block_type": "table",
    "content_for_embedding": "[Fees > Perps fee tiers]\nTable: Tier...",
    "source_url": "https://hyperliquid.gitbook.io/.../fees",
}

# 1. Embedding
vector = embedding_model.encode(chunk["content_for_embedding"])

# 2. 存储到 Vector DB
db.add(
    ids=[chunk["chunk_id"]],
    embeddings=[vector],
    metadatas=[{
        "heading_path": str(chunk["heading_path"]),
        "block_type": chunk["block_type"],
        "source_url": chunk["source_url"],
        "content": chunk["content_for_embedding"],
    }]
)
```

**Vector DB 的索引算法（HNSW）**：

```
HNSW：最主流的向量索引算法

原理：多层图索引
- Layer 2: 稀疏连接（快速筛选入口）
- Layer 1: 中等连接
- Layer 0: 密集连接（精确搜索）

搜索时：从顶层入口 → 多层跳转 → 找到最近邻
效果：近似 KNN，精度高，速度快（比暴力搜索快 50x+）
```

**主流 Vector DB 选择**：

| 数据库 | 特点 | 选型建议 |
|--------|------|---------|
| **Chroma** | 嵌入式/LAN，最简单 | **Phase 1 开发用** |
| **Qdrant** | 检索性能好，生产级 | 中等规模推荐 |
| **Pinecone** | 云服务，免运维 | 生产首选（贵）|
| **pgvector** | PostgreSQL 扩展 | 小规模/已有 PG |

**原始文档备份**：

```
/chroma_db/
├── embeddings/     # HNSW 索引文件
├── metadata.sqlite # SQLite，存 metadata
└── chunks/        # 可选：原始 chunk 备份

原始文档备份（用于重建 chunks）：
/raw_docs/
├── hyperliquid/fees.html
└── hyperliquid/trading.html
```

---

## Phase 6: 检索（Retrieval）

**目标**：根据用户 Query，从 Vector DB 中找到最相关的 Chunks

### 完整检索流程

```
用户: "Hyperliquid Gold tier 的 taker fee 是多少？"
    │
    ▼
Step 1: Query Embedding
  query text → embedding_model → query_vector (1024维)
    │
    ▼
Step 2: Vector Search
  query_vector → Chroma.search(query_vector, top_k=5)
    │
    ▼  HNSW 索引加速
Step 3: Vector DB 返回
  {
    'ids': ['chunk_003', 'chunk_001', 'chunk_007'],
    'distances': [0.23, 0.31, 0.45],
    'metadatas': [
      {'heading_path': '["Fees","Perps fee tiers"]', 'content': '...'},
      {'heading_path': '["Fees"]', 'content': '...'},
      {'heading_path': '["Fees","Maker rebates"]', 'content': '...'}
    ]
  }
    │
    ▼
Step 4: Rerank（可选）
  对 top-5 chunks 做二轮重排 → 更精准
    │
    ▼
Step 5: 组装 Prompt
  user question + retrieved chunks → LLM
    │
    ▼
Step 6: LLM Answer
  "Gold tier (Tier 3) taker fee is 0.0240%..."
```

### Vector Search 详解

```python
# Chroma 的 search 接口
results = chroma_collection.query(
    query_embeddings=[query_vector],
    n_results=5,          # top-k
    where={"block_type": "table"},  # 可选：元数据过滤
    include=["embeddings", "metadatas", "documents"]
)

# 返回的 documents 就是 Top-k Chunks 的原始 content
# Vector DB 返回的是：chunk_id + similarity_score + metadata
# metadata['content'] 才是用于组装 Prompt 的原始文本
```

### 为什么 Vector DB 返回的不是向量，而是文本？

```
存储阶段（离线）：
  chunk_text → embedding_model → vector → 存进 Vector DB
  存的是 vector + metadata（heading_path + content）

检索阶段（在线）：
  query_vector → Vector DB 内部做向量比较（通过 HNSW 索引）
  → 找出最近的 k 个
  → 返回对应的 metadata（原始文本）

Vector DB 内部原理：
  query_vector 和所有 stored_vectors 做相似度计算
  → 通过 HNSW 索引加速
  → 找出 top-k 最近邻
  → 返回对应的 chunk metadata（原始文本）
```

### Hybrid Search（可选增强）

```
纯向量搜索的问题：对关键词不敏感
  → "taker fee" 可能搜不到 "maker rebate"
  → 因为 "taker" 和 "maker" 向量相似度低

Hybrid Search = 向量搜索 + 关键词搜索（BM25）

原理：
  1. 向量搜索：捕捉语义相似性
  2. BM25 搜索：捕捉关键词精确匹配
  3. 两者结果融合（RRF / 加权）

适用场景：需要精确关键词匹配时（如技术术语、人名）
```

---

## Phase 7: Rerank（可选但推荐）

```
召回的 top-5 → Reranker 模型重排

原始: [Chunk 5(0.94), Chunk 2(0.71), Chunk 4(0.45), ...]
重排: [Chunk 5(0.98), Chunk 2(0.72), Chunk 4(0.40), ...]
      ↑ 分数调整，Chunk 5 依然是第一
```

**为什么需要 Rerank**：向量相似度不总是最准的，Reranker 能更好地判断"这个 chunk 是否真的回答了问题"。

---

## Phase 8: 生成（Generation）

```
┌─────────────────────────────────────────┐
│  Prompt 组装                            │
│                                         │
│  System: 你是 crypto 投研助手。          │
│  必须基于提供的上下文回答。              │
│  如果没有答案，说信息不足。              │
│  引用时标注来源。                        │
│                                         │
│  上下文（Top-k Chunks）:                │
│  [maker_rebates table content]          │
│                                         │
│  问题：Hyperliquid Gold tier 的          │
│        maker rebate 是多少？             │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  LLM 生成回答                           │
│                                         │
│  "根据费用结构文档，Hyperliquid 的       │
│  Maker rebate 取决于 14d weighted        │
│  maker volume，共 3 档：                │
│                                         │
│  - Tier 1 (>0.5%): -0.001%             │
│  - Tier 2 (>1.5%): -0.002%             │
│  - Tier 3 (>3.0%): -0.003%             │
│                                         │
│  来源: trading/fees (maker_rebates)     │
└─────────────────────────────────────────┘
```

---

## 关键洞察总结

### Parsing 核心洞察

> **Parsing 的关键在于保留完整的语法结构。**

```
语法结构天然携带语义信息：
- H1/H2/H3 = 语义层级
- 有序/无序列表 = 步骤/分类/并列概念
- 表格 = 结构化数据（行列关系本身就是数据）

长板趋势：处理器性能不断提高
→ 嵌套解析的性能消耗可忽略
→ 不设硬性上限，直接完整保留

Tradeoff：嵌套深度越深，递归处理越复杂
→ 真实文档嵌套几乎不超过 2 层
→ 实践中用递归循环处理即可，不需要硬上限
```

### Chunking 核心洞察

> **Chunking 的关键在于划分出区分度高的语义结构，以提高检索命中率。**

```
长板趋势：模型能力不断提高
→ 倾向于大 chunk，给 model 暴露更多 context
→ 模型能自己从大 chunk 中提取所需信息
→ 不需要提前在向量空间里过滤

切分策略：
- Table / Ordered_list：语法结构 = 语义结构 → 不按 token 量切
- Text：按 heading 聚合 → token > 4096 才切
- 核心原则：语义连贯优先于 token 量控制
```

---

## 与 Agent 的集成

```
用户查询
    │
    ▼
┌─────────────────────────────────────┐
│  Agent 识别需要查 RAG               │
│  "用户问费用结构" → 触发 RAG 查询   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  RAG Pipeline                       │
│  Query → Embed → Search → Rerank   │
│  → 组装 Prompt → LLM → Answer      │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Agent 综合输出                      │
│  结合 RAG 知识 + 实时 API 数据       │
│  → 完整投研分析报告                  │
└─────────────────────────────────────┘
```
