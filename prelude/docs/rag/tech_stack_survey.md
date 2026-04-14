# RAG Agent 技术栈尽职调查

> 调研日期：2026-04-03
> 目标：梳理主流 RAG/Agent 项目使用的技术栈，提供具体项目作为证明

---

## 一、技术栈全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM 应用技术栈                             │
├─────────────────────────────────────────────────────────────────┤
│  应用层                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ RAGFlow  │  │PrivateGPT│  │ FastGPT  │  │  Anything │       │
│  │(ragflow) │  │(私部署)  │  │(中文优化) │  │  LLM     │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                  │
│  框架层                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ LangChain│  │ LlamaIndex│  │  CrewAI  │  │  AutoGen │       │
│  │  (65k★)  │  │  (42k★)  │  │  (62k★) │  │  (36k★)  │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                  │
│  Embedding 层                                                      │
│  ┌──────────────────┐  ┌──────────────────┐                      │
│  │  OpenAI ada/bge  │  │  Cohere embed-v3 │                      │
│  │ sentence-trnsfmr │  │   Voyage AI     │                      │
│  └──────────────────┘  └──────────────────┘                      │
│                                                                  │
│  向量数据库层                                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐       │
│  │ Chroma │ │ Qdrant │ │Pinecone│ │ FAISS  │ │ Milvus │       │
│  │ (13k★)│ │ (13k★) │ │(商业)  │ │ (11k★)│ │ (12k★) │       │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘       │
│                                                                  │
│  LLM 推理层                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  vLLM    │  │  Ollama  │  │ Xinference│  │  llama.cpp│      │
│  │ (45k★)  │  │ (85k★)  │  │  (11k★) │  │ (40k★)  │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、主流 RAG 产品技术栈分析

### 2.1 PrivateGPT

**GitHub**: imartinez/privateGPT | **⭐ 26k**

| 组件 | 技术选型 | 备注 |
|------|---------|------|
| 框架 | **LlamaIndex** | 基于 LlamaIndex 构建 RAG |
| API 层 | FastAPI | 提供 OpenAI API 兼容接口 |
| 向量库 | **Qdrant**（默认）/ Chroma | 支持多 Vector DB 切换 |
| LLM | LlamaCPP / OpenAI / LocalAI | 支持本地私部 |
| Embedding | OpenAI ada / 本地模型 | 通过 LlamaIndex 接口抽象 |
| 特点 | 专注私部署、离线 RAG、API-first 设计 |

**架构**：

```
API 层 (FastAPI, OpenAI-compatible)
├── High-level API: 文档摄取 + Chat/Completions
└── Low-level API: Embedding 生成 + 上下文检索

RAG 引擎 (LlamaIndex)
├── LLM Component (LlamaCPP / OpenAI)
├── Embedding Component
└── VectorStore Component (Qdrant / Chroma)

关键设计: 依赖注入 + LlamaIndex 抽象接口，便于切换底层实现
```

---

### 2.2 RAGFlow

**GitHub**: infiniflow/ragflow | **⭐ 14k**

| 组件 | 技术选型 | 备注 |
|------|---------|------|
| 向量库 | **Elasticsearch**（默认）/ Infinity | 企业级检索 |
| LLM | 多提供商（GPT-5/Gemini 3 Pro 等）| 配置化 |
| Embedding | 外部 embedding 服务 | 配置灵活 |
| 分块策略 | **Template-based chunking** | 基于模板的智能分块 |
| 特点 | DeepDoc 文档理解、converged context engine、多路召回与融合重排序 |

**架构亮点**：
- 强调**文档理解**（不只是 chunking）：表格、图表、流程图的深度解析
- 多路召回：向量检索 + 关键词检索 → 融合重排
- **Template-based chunking**：针对不同类型文档（论文/合同/表格）使用不同分块模板

---

### 2.3 LangChain-Chatchat

**GitHub**: chatchat-space/Langchain-Chatchat | **⭐ 40k+** | 中文优化

| 组件 | 技术选型 | 备注 |
|------|---------|------|
| 框架 | **LangChain** | 核心框架 |
| 向量库 | **FAISS**（默认）/ Milvus / Elasticsearch | 中文 embedding |
| Embedding | **bge-large-zh-v1.5**（默认）| 中文优化 |
| LLM | Xinference / LocalAI / Ollama / FastChat | 支持国产模型 |
| 前端 | **Streamlit** | WebUI |
| API 层 | FastAPI | Python FastAPI 后端 |

**分块策略**：文本分割（基于规则 + token 计数）

---

### 2.4 FastGPT

**GitHub**: labring/FastGPT | **⭐ 18k**

| 组件 | 技术选型 | 备注 |
|------|---------|------|
| 框架 | 自研（非 LangChain）| 从零构建，定制性强 |
| 向量库 | **Chroma**（内置）/ PGvector | 轻量级首选 |
| Embedding | OpenAI ada / BGE | 支持多模型 |
| API 层 | FastAPI | |
| 前端 | Next.js（较新版本）| |
| 特点 | 完整的 RAG + Agent 能力、Flow 可视化编排 |

---

### 2.5 GPT4All

**GitHub**: nomic-ai/gpt4all | **⭐ 30k**

| 组件 | 技术选型 | 备注 |
|------|---------|------|
| LLM | **llama.cpp** 实现 | 本地 CPU/GPU 运行 |
| 向量库 | **Weaviate**（集成）| |
| Embedding | 多模型支持 | 通过 LangChain 集成 |
| 特点 | 专注本地 LLM 推理，边缘部署友好 |

---

### 2.6 Flowise

**GitHub**: FlowiseAI/Flowise | **⭐ 12k**

| 组件 | 技术选型 | 备注 |
|------|---------|------|
| 框架 | **LangChain** | 基于 LangChain JS |
| 前端 | **React** | 低代码 UI |
| 后端 | **Node.js + Express** | TypeScript monorepo |
| 向量库 | Chroma / FAISS / Pinecone | 多选一 |
| Embedding | OpenAI ada / Local | |
| 特点 | **低代码/无代码**：拖拽式编排 RAG 流程 |

**架构**：

```
packages/
├── server      # Node.js Express API
├── ui          # React 前端
├── components  # LangChain 第三方节点
└── api-documentation
```

---

## 三、框架层分析

### 3.1 LangChain

**GitHub**: langchain-ai/langchain | **⭐ 65k**

| 维度 | 内容 |
|------|------|
| 定位 | LLM 应用开发框架（不仅仅是 RAG）|
| 架构 | LCEL（LangChain Expression Language）链式表达 |
| RAG 特有 | LangChain Text Splitters、VectorStore 集成、RetrievalQA |
| Embedding | 内置 OpenAI / HuggingFace embedding 封装 |
| Vector DB | Chroma / FAISS / Pinecone / Qdrant / Milvus 等 10+ |
| Agent | Tools / Agents / Memory / Callbacks 完整抽象 |
| 优点 | 生态最大、集成最多、社区活跃 |
| 缺点 | 抽象层级高、定制复杂、版本迭代快（breaking changes 多）|

---

### 3.2 LlamaIndex

**GitHub**: run-llama/llama_index | **⭐ 42k**

| 维度 | 内容 |
|------|------|
| 定位 | **检索优先**，专注文档索引和检索 |
| 架构 | Query Engine → Retriever → Node（数据单元）|
| RAG 特有 | **Retrieval + Augmentation + Generation** 完整抽象 |
| Embedding | 内置多种 Embedding 模型封装 |
| Vector DB | Chroma / FAISS / Pinecone / Qdrant / Weaviate |
| 与 LangChain 区别 | LlamaIndex = retrieval-first；LangChain = orchestration-first |
| 优点 | RAG 场景更专注、接口更清晰 |
| 缺点 | 生态比 LangChain 小 |

**对比**：

| | LangChain | LlamaIndex |
|--|-----------|-------------|
| 定位 | 通用 LLM 应用框架 | 检索优先的 RAG 框架 |
| 核心抽象 | Chain / Tool / Agent | Query Engine / Retriever / Node |
| RAG 适合度 | 一般（框架太泛）| **更适合**（retrieval-first 设计）|
| 学习曲线 | 陡（组件太多）| 中等 |
| 定制难度 | 难（抽象层级高）| 中等 |

---

### 3.3 CrewAI

**GitHub**: crewaiinc/crewai | **⭐ 62k**

| 维度 | 内容 |
|------|------|
| 定位 | **Multi-Agent 编排框架**（role-based）|
| 架构 | Agent → Task → Crew → Process |
| 与 LangChain | **完全独立**，从零构建 |
| Agent 抽象 | Role / Goal / Backstory → 自驱型 Agent |
| 工具集成 | LangChain Tools / 自定义 Tools |
| 记忆 | 内置记忆机制（短期/长期）|
| 优点 | 多 Agent 场景简洁、角色定义直观 |
| 缺点 | 单 Agent 场景过重、定制需要深入源码 |

---

### 3.4 AutoGen

**GitHub**: microsoft/autogen | **⭐ 36k**

| 维度 | 内容 |
|------|------|
| 定位 | **Multi-Agent 对话框架**（微软出品）|
| 架构 | Agent ↔ Agent（对话驱动）|
| 核心概念 | ConversableAgent / GroupChat |
| 与 LangChain | 可集成，非竞争关系 |
| 优点 | 多 Agent 对话场景成熟、微软生态加持 |
| 缺点 | 对话式设计不通用所有场景 |

---

## 四、Embedding 模型对比

| 模型 | 维度 | Context | 特点 | 适合场景 |
|------|------|---------|------|---------|
| **text-embedding-3-small** | 1536 | 8K | OpenAI 最新，便宜 | 快速原型 |
| **text-embedding-3-large** | 3072 | 8K | OpenAI 最新，最准 | 精度优先 |
| **bge-m3** (BAAI) | 1024 | 8K | 多语言 + 开源 | **首选本地** |
| **bge-large-zh-v1.5** | 1024 | 512 | 中文优化 | 中文文档 |
| **e5-mistral-7b** | 4096 | 4K | 英文效果好 | 英文为主 |
| **Cohere embed-v3** | 1024 | 8K | 多语言 + 多语言 | 企业首选 |
| **NV-Embed-v2** | 1024 | 128K | 长文档 | 超长文本 |

**业界实际使用情况**：
- 英文场景：`text-embedding-3-small` / `bge-m3` / `Cohere`
- 中文场景：`bge-large-zh-v1.5` / `text-embedding-3-small`
- Crypto 文档（英文为主）：`bge-m3` 或 `text-embedding-3-small`

---

## 五、向量数据库对比

| 数据库 | Stars | 存储方式 | 索引算法 | 特点 | 选型建议 |
|--------|-------|---------|---------|------|---------|
| **Chroma** | 13k | 嵌入式/LAN | HNSW | 最简单，开发首选 | **Phase 1** |
| **Qdrant** | 13k | K-V 存储 | HNSW + 过滤 | 检索性能好 | 中等规模 |
| **FAISS** | 11k | 内存/磁盘 | IVF/HNSW | Meta 出品，快速 | 已有 PF 才用 |
| **Pinecone** | - | 云服务 | 闭源 | 免运维，贵 | 生产（不差钱）|
| **Milvus** | 12k | 分布式 | IVF/HNSW | 大规模，国产 | 大规模/国产 |
| **Weaviate** | 11k | 图数据库 | 混合 | GraphQL | 复杂查询 |
| **pgvector** | - | PostgreSQL | IVFFlat/HNSW | 已有 PG 首选 | 小规模过渡 |

**Chroma 适合 Phase 1 的原因**：单文件、零配置、Pythonic API。迁移成本低（接口和 Qdrant / Pinecone 类似）。

---

## 六、LLM 推理框架对比

| 框架 | Stars | 支持模型 | 特点 | 适合场景 |
|------|-------|---------|------|---------|
| **Ollama** | 85k | Llama/Mistral/Gemma 等 | 一键启动，本地推理 | 本地 / Mac |
| **vLLM** | 45k | GPTQ/GGUF | 高吞吐，PagedAttention | 生产推理 |
| **llama.cpp** | 40k | GGUF 格式 | CPU/GPU，边缘部署 | 边缘/嵌入式 |
| **Xinference** | 11k | 多模型统一接口 | 企业级，支持分布式 | 生产 |
| **LocalAI** | 20k | 兼容 OpenAI API | 自托管 | 私部署 |

---

## 七、低抽象 vs 高抽象技术栈

### 低抽象（自己拼，定制强）

```
Crawling:     Playwright + BeautifulSoup
Parsing:      markdownify + 自研 MarkdownBlock Parser
Chunking:     自研（按 heading 边界切分）
Embedding:    sentence-transformers (BGE-m3)
Vector DB:    Chroma（开发）/ Qdrant（生产）
LLM 调用:     openai SDK / anthropic SDK
编排:         FastAPI 自己组装
```

**代表项目**：PrivateGPT（内部用 LlamaIndex，但也可以完全自己拼）

---

### 高抽象（一行启动，快速原型）

```
全套:         LangChain / LlamaIndex 框架
Embedding:    LangChain Embeddings 封装
Vector DB:    LangChain VectorStore 封装
LLM:          LangChain LLMs 封装
```

**代表项目**：Flowise（拖拽式，零代码）、FastGPT（开箱即用）

---

### 不同抽象层级对比

| 抽象层级 | 代表工具 | 优点 | 缺点 | 适合阶段 |
|---------|---------|------|------|---------|
| **零抽象** | 自己拼所有组件 | 完全可控，细节透明 | 代码量大 | 学习/定制需求 |
| **中抽象** | LlamaIndex / LangChain | 平衡灵活性和便利性 | 需理解框架逻辑 | **Phase 1-2** |
| **高抽象** | Flowise / FastGPT | 10 行跑通 | 定制困难，抽象泄露 | 快速原型 |

---

## 八、推荐技术栈

### 方案 A：底层自己拼（学习 + 定制）

```
Crawling:     Playwright + BeautifulSoup
HTML→MD:      markdownify
Parsing:      自研 MarkdownBlock Parser
Chunking:     自研（按 heading + token 双重规则）
Embedding:    sentence-transformers (BAAI/bge-m3)
Vector DB:    Chroma
LLM:          OpenAI API (gpt-4o-mini)
API 层:       FastAPI
```

### 方案 B：LlamaIndex 中抽象（平衡）

```
框架:         LlamaIndex（Retrieval + Query Engine）
Embedding:    OpenAI ada / BGE-m3
Vector DB:    Chroma / Qdrant
Crawling:     Playwright
Parsing:      自研（保持 block 结构优势）
Chunking:     自定义 Node Parser（LlamaIndex 支持）
LLM:          OpenAI API
API 层:       FastAPI
```

### 方案 C：框架全托（快速原型）

```
框架:         LangChain + LangChain Embeddings + LCEL
Embedding:    OpenAI ada
Vector DB:    Pinecone
LLM:          OpenAI API
API 层:       LangServe
前端:         LangServe UI / FastGPT
```

---

## 九、技术选型建议

| 考虑维度 | 建议 |
|---------|------|
| **学习目的** | 方案 A（自己拼，理解每个环节）|
| **Phase 1 验证** | 方案 B（LlamaIndex 为主，Parsing/Chucking 自研）|
| **快速出 Demo** | 方案 C（Flowise 或 FastGPT）|
| **Crypto 文档** | BGE-m3 Embedding + Chroma + 自研 Parsing |
| **后续 Multi-Agent** | CrewAI 或 AutoGen（Phase 3 再引入）|

**不建议直接用 LangChain 全家桶的原因**：抽象层级过高，框架迭代快，容易被锁死。Phase 1 用 LlamaIndex 做检索层，Agent 层到 Phase 3 再引入 CrewAI。

---

## 十、参考资料

- [PrivateGPT Architecture](https://docs.privategpt.dev/)
- [RAGFlow 技术博客](https://ragflow.io/blog)
- [LangChain vs LlamaIndex (Statsig)](https://www.statsig.com/perspectives/llamaindex-vs-langchain-rag)
- [a16z: Emerging Architectures for LLM Applications](https://a16z.com/p/emerging-architectures-for-llm-applications)
- [CrewAI Multi-Agent Analysis](https://dev.to/foxgem/ai-agent-memory-a-comparative-analysis-of-langgraph-crewai-and-autogen-31dp)
