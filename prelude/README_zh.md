# Prelude（前奏）

> Crypto research agent 系列 - RAG + 极简 Agent 实验场

[English](README.md) | [中文](README_zh.md)

Crypto research agent 系列的第一篇。用极简技术栈验证核心的 RAG + Agent 能力。

## 架构

```
用户 → Pi-mono TUI（交互层）
       │
       ▼
Python 极简 Agent（~500 行）
       │
       ├── rag_search / bash / read / write
       │
       ▼
RAG Pipeline: 爬虫 → 解析器 → 分块器 → BGE-m3 → Chroma
```

## 工具链

| 组件 | 工具 |
|------|------|
| Python 包管理 | [uv](https://github.com/astral-sh/uv) |
| Node.js 包管理 | [pnpm](https://pnpm.io/) |

### 1. 安装依赖

```bash
cd prelude

# Python 依赖（uv）
uv sync

# 安装 Playwright 浏览器
uv run playwright install chromium

# TUI 依赖（pnpm）
cd tui && pnpm install && cd ..
```

> **提示**：如果偏好 pip，可用 `pip install -e .` 代替。

### 2. 配置环境

```bash
# 复制环境模板
cp .env.example .env

# 编辑 .env 并添加 API 密钥
vim .env
```

### 3. 构建索引

```bash
# 推荐：从当前配置的数据源全量重建索引
python scripts/build_index.py --rebuild
```

> **提示**：高级/恢复模式请查看 `scripts/build_index.py` 顶部注释，或运行 `python scripts/build_index.py --help`。
> 抓取源字段说明见 `config/README.md`。

### 4. 启动 Agent

```bash
# TUI 模式（推荐）— 先构建后运行
cd tui && pnpm build && node dist/index.js

# CLI 模式（无 TUI）
python main.py
```

> **行为说明**：TUI bridge 会先启动，向量库/Embedding 模型改为懒加载（首次触发 `rag_search` 时加载）。
> 如果检索初始化/搜索失败，工具会返回 `RAG_UNAVAILABLE`，助手应明确报错而不是凭记忆回答。
> Embedding 加载策略为“本地优先”：优先使用本地 HuggingFace 缓存快照（`local_files_only=True`），再尝试远程下载。

## .env 配置

复制 `.env.example` 到 `.env` 并配置：

```bash
# MiniMax API
ANTHROPIC_AUTH_TOKEN=你的_token_此处
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic

# 模型
MODEL=MiniMax-M2.7

# 向量库
VECTORSTORE_DIR=./data/vectorstore

# 可选：运行时嵌入模型覆盖
# 运行时默认嵌入模型为 BAAI/bge-m3
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# 可选：懒加载失败后的重试冷却时间（秒）
VECTORSTORE_RETRY_INTERVAL_SEC=30
```

## RAG_UNAVAILABLE 排查

- 先看模型设置：`.env` 里的 `EMBEDDING_MODEL` 会覆盖运行时默认值（`BAAI/bge-m3`）。
- 索引构建模型与运行时模型需要一致，否则可能触发向量维度不匹配。
- 对于已缓存模型，运行时现在会优先使用本地 HF 快照，不依赖联网下载。

## Anthropic SDK + MiniMax

MiniMax 支持标准 Anthropic SDK：

```python
import anthropic

client = anthropic.Anthropic(
    api_key="your_token",
    base_url="https://api.minimax.io/anthropic",  # 国际版
    # base_url="https://api.minimaxi.com/anthropic",  # 国内版
)

response = client.messages.create(
    model="MiniMax-M2.7",
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Hello"}],
    tools=[...],
)
```

## 项目结构

```
prelude/
├── tui/                            # TypeScript TUI（pi-tui）
│   ├── src/index.ts                # 聊天界面，作为 subprocess 生成 bridge
│   ├── package.json                # pnpm 管理，依赖 @mariozechner/pi-tui
│   └── tsconfig.json
├── app/                            # 运行时应用层
│   ├── agent/                      # 极简 Agent Loop + 工具
│   └── bridge/                     # JSONL 桥接（由 TUI 生成为 subprocess）
├── rag/                            # RAG pipeline 层
│   ├── crawlers/                   # HTML 抓取
│   ├── parsers/                    # HTML/Markdown 解析
│   ├── chunkers/                   # 语义分块
│   └── embedders/                  # 向量化与存储
├── config/
│   ├── craw_list.yaml              # 抓取源注册表
│   └── rag_pipeline.yaml           # RAG 管线默认参数
├── data/                           # Pipeline 产物与向量库
├── scripts/
│   └── build_index.py             # 索引构建脚本
├── main.py                        # CLI 降级模式（无 TUI）
├── pyproject.toml
├── uv.lock
├── .env.example
└── README.md
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Python 环境 | uv |
| TUI | @mariozechner/pi-tui（TypeScript/pnpm） |
| Agent Loop | 自研（~500 行）+ Anthropic SDK |
| LLM | MiniMax-M2.7 |
| 爬虫 | Playwright |
| 解析器 | 自研 MarkdownBlock |
| 嵌入模型 | BGE-m3 |
| 向量库 | Chroma |

## Crypto Research Agent 系列

| 名称 | 含义 | 状态 |
|------|------|------|
| **prelude** | 前奏 | 当前 |
| **nocturne** | 夜曲 | 下一步 |
| **sonata** | 奏鸣曲 | 稍后 |
| **symphony** | 交响曲 | 最终 |

## 参考资源

- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) - 极简 Agent Loop 参考
- [pi-mono](https://github.com/badlogic/pi-mono) - TUI 参考
- [Anthropic SDK](https://docs.anthropic.com/) - Anthropic SDK 文档
- [BGE-m3](https://huggingface.co/BAAI/bge-m3) - 嵌入模型
- [Chroma](https://github.com/chroma-core/chroma) - 向量库
