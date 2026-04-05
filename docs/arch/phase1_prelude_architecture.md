# Phase 1: RAG + Minimal Agent 架构设计

> 目标：构建一个工业级 RAG 知识库的 toy 原型 + Minimal Agent
> 定位：验证 RAG pipeline + Agent 协作能力

---

## 系列命名：乐章（Musical Movements）

> 致敬 Claude 的 Haiku/Sonnet/Opus，用乐章作为 Agent 能力层级的隐喻。

| 名称 | 含义 | 定位 |
|------|------|------|
| **prelude** | 前奏 | 实验场，验证核心能力 |
| **nocturne** | 夜曲 | 沉思，面向复杂推理 |
| **sonata** | 奏鸣曲 | 成熟框架，结构化 |
| **symphony** | 交响曲 | 生产平台，多 Agent 协奏 |

```
prelude/   ← 当前，pi-mono + minimal agent
nocturne/  ← 后续，LangGraph 探索
sonata/    ← 更远，CrewAI 等成熟框架
symphony/  ← 最终，production platform
```

**prelude** 是开场，是实验，但自有节奏。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      User (Terminal)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Pi-mono TUI                             │
│               （仅做交互层，展示输入/输出）                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Minimal Agent (~500 行 Python)                  │
│                                                              │
│   agent_loop:                                               │
│     messages → LLM API → tool_calls → handlers            │
│                    ↑                                        │
│                    └── rag_search tool                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  RAG Pipeline (Python)                     │
│                                                              │
│  Crawler → Markdown Parser → Semantic Chunker              │
│                                    → BGE-m3 → Chroma       │
└─────────────────────────────────────────────────────────────┘
```

---

## 分层说明

### Layer 1: Pi-mono TUI（仅交互层）

```
职责：
- 用户输入/输出展示
- 调用 Python Agent（通过 stdio/RPC）
- 不做 executor/reflector 逻辑

选择理由：
- Pi-mono TUI 交互体验好
- TypeScript/Node.js，不参与核心逻辑
- 只做展示层，语言隔离不是问题
```

### Layer 2: Minimal Agent（Python，~500 行）

```
核心：复刻 learn-claude-code 的极简 Agent Loop

伪代码：
while True:
    response = llm.chat(
        model=MODEL,
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=TOOL_DEFINITIONS,
    )
    
    if response.stop_reason == "tool_use":
        for tool_call in response.tool_calls:
            result = TOOL_HANDLERS[tool_call.name](**tool_call.input)
            messages.append(tool_result(tool_call.id, result))
    else:
        return response.content


Tools：
├── rag_search        # RAG 检索
├── bash              # 执行命令
├── read_file         # 读文件
└── write_file        # 写文件
```

### Layer 3: RAG Pipeline（Python）

```
流程：
GitBook URL → Playwright Crawler → HTML
    → Markdown Parser → MarkdownBlock[]
    → Semantic Chunker → Document[]
    → BGE-m3 Embedding → Chroma

职责：
- 索引构建（离线）
- 供 Agent 调用（rag_search tool）
```

---

## 技术栈

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| **Agent Loop** | 自写 (~500行) | 极简，复刻 learn-claude-code |
| **TUI** | Pi-mono | 仅做交互层 |
| **LLM** | MiniMax M2-her | 64K context，OpenAI 兼容 |
| **Crawler** | Playwright + BeautifulSoup | JS 渲染 GitBook |
| **Parser** | 自研 MarkdownBlock Parser | 保留语法结构 |
| **Chunker** | 自研 Semantic Chunker | heading 边界切分 |
| **Embedding** | BGE-m3（本地）| 开源免费，多语言 |
| **Vector DB** | Chroma | 嵌入式，最简 |

---

## RAG Pipeline 详细设计

### 3.1 Crawler

```
输入：GitBook URL（https://hyperliquid.gitbook.io/hyperliquid-docs/）
输出：原始 HTML 文件列表

技术：
- Playwright（JS 渲染）
- BeautifulSoup（HTML 解析）

实现：
- 递归爬取所有子页面
- 存储原始 HTML 到本地
```

### 3.2 Markdown Parser

```
输入：原始 HTML
输出：list[MarkdownBlock]

技术：
- markdownify（HTML → Markdown）
- 自研 MarkdownBlock 解析器

数据结构：
class MarkdownBlock:
    block_id: str
    heading_path: list[str]   # ["Fees", "Perps fee tiers"]
    heading_level: int        # H1=1, H2=2, H3=3
    block_type: str            # "text" | "table" | "code" | "ordered_list" | "unordered_list"
    content: str | None
    items: list | None         # for lists
    table_headers: list | None
    table_rows: list | None
    code: str | None
    code_lang: str | None
```

### 3.3 Semantic Chunker

```
输入：list[MarkdownBlock]
输出：list[Document]

策略：
- 按 heading_path 聚合 blocks
- Text blocks：按 heading 边界切分
- Table blocks：整表一个 chunk（不检查 token）
- Code blocks：整个函数一个 chunk
- flatten_block() 生成 embedding 文本

输出 LangChain Document：
- page_content: embedding 文本
- metadata: heading_path, block_type, source_url
```

### 3.4 Embedding + VectorStore

```
Embedding: BAAI/bge-m3（sentence-transformers）
Vector DB: Chroma（嵌入式）

存储：
documents → BGE-m3.encode() → Chroma.from_documents()
```

---

## Minimal Agent 设计

### Tool 定义

```python
TOOLS = [
    {
        "name": "rag_search",
        "description": "Search the crypto documentation knowledge base",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "bash",
        "description": "Execute a bash command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_file",
        "description": "Read a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    },
]
```

### Tool Handlers

```python
TOOL_HANDLERS = {
    "rag_search": rag_search_handler,
    "bash": bash_handler,
    "read_file": read_file_handler,
    "write_file": write_file_handler,
}

def rag_search_handler(query: str, top_k: int = 5) -> str:
    """RAG 检索"""
    query_vec = embedding_model.encode(query)
    results = vectorstore.query(query_embeddings=[query_vec], n_results=top_k)
    chunks = [r['metadata'][0]['content'] for r in results]
    return "\n---\n".join(chunks)
```

### System Prompt

```
SYSTEM_PROMPT = """You are a crypto research assistant.
You have access to tools for searching documentation and executing commands.
Use rag_search to find information about crypto protocols.
Be precise and cite sources in your answers.
"""
```

---

## Pi-mono 集成方式

```
Pi-mono 只做 TUI，不做 executor：

1. Python Agent 作为 Pi-mono 的"backend"
2. Pi-mono 通过 stdio/RPC 调用 Python Agent
3. Python Agent 返回结果给 Pi-mono 展示

桥接方式：
- Python Agent 暴露 stdio 接口
- Pi-mono TUI 通过 subprocess 调用
- 或者 Python Agent 改成 HTTP 服务，Pi-mono 通过 HTTP 调用
```

---

## 项目结构

```
prelude/
├── crawlers/
│   └── gitbook_crawler.py      # Playwright 爬虫
├── parsers/
│   ├── html_to_markdown.py      # HTML → Markdown
│   └── markdown_parser.py       # Markdown → MarkdownBlock
├── chunkers/
│   └── semantic_chunker.py      # MarkdownBlock → Document
├── embedders/
│   └── embedding_pipeline.py    # Document → Chroma
├── agent/
│   ├── agent_loop.py           # Minimal Agent Loop (~500行)
│   ├── tools.py                # Tool definitions + handlers
│   └── system_prompt.py        # System prompt
├── bridge/
│   └── pi_bridge.py           # Pi-mono TUI 桥接
├── main_index.py               # 索引构建入口
├── main_chat.py                # Chat 入口
└── requirements.txt
```

---

## 实现步骤

```
Step 1: RAG Pipeline
  - Playwright 爬取 Hyperliquid 文档
  - Markdown Parser 解析
  - BGE-m3 + Chroma 存储
  - 验证检索结果

Step 2: Minimal Agent
  - 复刻 agent_loop
  - 实现 rag_search tool
  - 接入 MiniMax M2-her
  - 验证 tool calling

Step 3: Pi-mono 集成
  - 桥接 Python Agent → Pi-mono TUI
  - 完整交互流程

Step 4: 扩展数据源
  - 添加更多交易所文档
  - 验证跨文档检索
```

---

## Toy 级别的限制

```
已实现（工业级基础）：
✓ Markdown 文档解析
✓ Semantic chunking（heading 边界）
✓ BGE-m3 embedding
✓ Chroma vector DB
✓ Minimal Agent loop
✓ Tool calling
✓ Pi-mono TUI 交互

未实现（后续扩展）：
✗ HTML/图片/视频 等非 Markdown 数据
✗ 多粒度 chunking 策略
✗ 增量更新和过期淘汰
✗ 多语言文档（目前专注英文）
✗ 多 Agent 协作
```

---

## 待验证假设

```
1. BGE-m3 对 Crypto 术语理解足够
2. Semantic Chunker 的 heading 切分策略有效
3. M2-her 支持 function calling（MiniMax API）
4. Pi-mono 可以桥接 Python Agent
5. Minimal Agent loop (~500行) 能稳定运行
```

---

## 参考项目

- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)：Minimal Agent Loop 参考
- [pi-mono](https://github.com/badlogic/pi-mono)：TUI 参考
- [BGE-m3](https://huggingface.co/BAAI/bge-m3)：Embedding 模型
- [Chroma](https://github.com/chroma-core/chroma)：Vector DB
