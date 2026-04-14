# RAG 数据源与数据类型分析

## 数据源清单

### 1. 白皮书（核心非结构化数据）

| 来源 | 内容 | 格式 | 处理难度 |
|------|------|------|---------|
| AllCryptoWhitepapers.com | 3900+ 白皮书直链 | PDF / HTML | 高 |
| CoinGecko 白皮书链接 | 项目官方白皮书 | PDF / Markdown | 中 |
| 项目官网 Docs | 项目文档 | HTML | 高 |

**数据类型**：
- 纯文本（段落、章节）
- 表格（代币分配、解锁时间表）
- 图表（饼图、折线图）
- 图片（logo、流程图）
- 结构化数据（代币经济学参数）

---

### 2. 链上数据（结构化 → 半结构化）

| 来源 | 内容 | 格式 | 处理难度 |
|------|------|------|---------|
| Dune Analytics | SQL 查询结果 | JSON / CSV | 低 |
| DeFiLlama | TVL / 协议指标 | JSON | 低 |
| Etherscan | 合约 ABI / 交易历史 | JSON | 中 |
| Tokenomist | 解锁时间表 | JSON / HTML | 中 |

**数据类型**：
- 数值型指标（TVL、交易量、持有人数）
- 时间序列（价格、链上活跃度）
- 关系型（地址 ↔ 合约 ↔ 项目）

---

### 3. 行情数据（结构化）

| 来源 | 内容 | 格式 | 处理难度 |
|------|------|------|---------|
| CoinGecko | 价格、市值、交易所数据 | JSON | 低（API 直出）|
| CoinMarketCap | 基本面数据 | JSON | 低 |
| CoinDesk | 新闻与价格 | JSON / HTML | 中 |

**注意**：行情数据实时性强，通常走 API 直查，不进 RAG 管道。但历史行情报道、宏观分析文章需要 RAG 处理。

---

### 4. 社区/舆情数据（非结构化）

| 来源 | 内容 | 格式 | 处理难度 |
|------|------|------|---------|
| Reddit | 讨论帖、AMA | HTML | 高 |
| Twitter/X | 推文 threads | JSON / HTML | 高 |
| Bitcointalk | 论坛帖子 | HTML | 高 |
| TradingView | 分析文章 | HTML | 中 |

---

### 5. 第三方研究报告（高价值非结构化）

| 来源 | 内容 | 格式 | 处理难度 |
|------|------|------|---------|
| Messari | 研究报告 | PDF / HTML | 高 |
| Delphi Digital | 深度分析 | PDF / HTML | 高 |
| CoinDesk Indices | 指数 methodology | PDF | 高 |

---

## 数据类型分类

### 结构化数据（机器友好，RAG 不是首选）

```
JSON / CSV / SQL
├── 数值指标：TVL, 价格, 流通量
├── 时间序列：K线, 链上活跃度
└── 关系数据：持仓地址, 合约关系
```

**处理方式**：直接解析 → 存入 DB（SQLite/PostgreSQL）→ 分析工具查询

---

### 半结构化数据（RAG 需预处理）

```
HTML / Markdown / LaTeX
├── 有明确结构但不打平
├── 嵌套标签 / 元数据
└── 示例：白皮书 HTML 版本、Dune 查询结果
```

**处理方式**：
- HTML：BeautifulSoup / Trafilatura 提取文本 + 结构
- Markdown：解析标题层级，保留 table/blockquote
- LaTeX：Pandoc 转换，保留公式上下文

---

### 非结构化数据（RAG 核心难题）

#### 文本类
- 长段落（白皮书正文、分析文章）
- 多语言混杂（英文白皮书 + 中文社区讨论）
- 专业术语密集（金融 / 合约 / DeFi 术语）

#### 表格类
- 简单表格（代币分配、团队分配）→ 保留行列结构
- 复杂表格（多层表头、合并单元格）→ 需要 layout analysis
- 横向大表格（时间序列，多个项目对比）→ 切分策略要设计

#### 图表类 ← 最头疼
```
├── 饼图 / 柱状图（代币分配比例）
├── 折线图（解锁时间表、价格走势）
├── 流程图（合约架构、治理流程）
└── 网络图（项目关系、代币流转）
```

**处理方式**：
- Vision Model（GPT-4V / Claude）生成 caption + 提取数据
- 专用工具（Plotly extractor, chart parser）提取原始数据
- 图表转 Markdown 表格，作为结构化 chunk 存入 RAG

#### 图片类
- Logo、品牌图 → 存引用，不做 embedding
- 截图（Twitter discussion、K线）→ OCR + Vision caption
- 概念图（架构图、流程图）→ Vision 描述 + 存入 RAG

#### PDF 类 ← 最复杂
```
├── 扫描件（纯图片）→ OCR
├── 原生 PDF（文本可选中）
│   ├── 文字层 → 提取文本
│   ├── 表格层 → layout analysis 提取
│   └── 图片层 → Vision 处理
└── 混合（文字 + 表格 + 图片 + 公式）
```

**处理工具**：
- PyMuPDF（快速文本提取）
- LayoutPDFReader（表格 + layout 分析）
- Nougat（公式检测，学术型 PDF）

---

## 非结构化数据处理优先级

| 类型 | 优先级 | 原因 | 技术方案 |
|------|--------|------|---------|
| 白皮书正文文本 | P0 | 核心知识来源 | PDF 解析 + chunking |
| 白皮书表格 | P0 | 关键数据（代币分配、解锁）| LayoutPDF + table extraction |
| 项目文档 HTML | P1 | 实时性要求高 | Trafilatura / BeautifulSoup |
| 图表（代币图、流程图）| P1 | 信息密度高 | Vision caption |
| 舆情帖（Reddit/Twitter）| P2 | 噪声大，按需引入 | 特定 selector 提取 |
| 研究报告 PDF | P2 | 质量高但量大 | 同白皮书处理流程 |

---

## 清洗与接入流程

```
原始数据
    │
    ├── PDF ──────────→ PyMuPDF + LayoutPDFReader ──→ 文本 + 表格 + 图片
    ├── HTML ─────────→ Trafilatura / BeautifulSoup ──→ 纯文本 + 链接 + 结构
    ├── 图片 ─────────→ Vision Model ──→ Caption + OCR
    └── JSON（API）──→ Pydantic 解析 ──→ 结构化存储（不进 RAG）
          │
          ▼
    标准化的 Chunks
    │
    ├── text_chunk: 纯文本块（512-1024 tokens）
    ├── table_chunk: 保留行列结构的表格（JSON 序列化）
    ├── image_chunk: 图片引用 + Vision caption
    └── metadata: 来源、日期、项目名、chunk 类型
          │
          ▼
    Embedding（text-embedding-3-small / bge-m3）
          │
          ▼
    Vector DB（Chroma / LanceDB / Pinecone）
          │
          ▼
    原始文件存档（OSS / S3，保留原始格式）
```

---

## 当前阶段决策点

1. **白皮书先接哪个来源**：AllCryptoWhitepapers（量大）还是 CoinGecko（质量相对高）？
2. **PDF 解析工具选型**：PyMuPDF（快但粗糙）vs LayoutPDFReader（慢但准）？
3. **Vision Model 用哪个**：Claude（准但贵）/ GPT-4V（贵）/ 开源方案？
4. **图表处理策略**：Phase 1 先跳过图表，还是先做 caption？
