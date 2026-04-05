# Prelude

> Opening movement - RAG + Minimal Agent experimental playground

[English](README.md) | [中文](README_zh.md)

First chapter of the Musical Movements series. Verifying core RAG + Agent capabilities with a minimalist tech stack.

## Architecture

```
User -> Pi-mono TUI (interaction layer)
         |
         v
Python Minimal Agent (~500 lines)
         |
         +-- rag_search / bash / read / write
         |
         v
RAG Pipeline: Crawler -> Parser -> Chunker -> BGE-m3 -> Chroma
```

## Tooling

| Component | Tool |
|-----------|------|
| Python Package Manager | [uv](https://github.com/astral-sh/uv) |
| Node.js Package Manager | [pnpm](https://pnpm.io/) |

### 1. Install Dependencies

```bash
cd prelude

# Python dependencies (uv)
uv sync

# Install Playwright browser
uv run playwright install chromium

# TUI dependencies (pnpm)
cd tui && pnpm install && cd ..
```

> **Note**: If you prefer pip, use `pip install -e .` instead.

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API key
vim .env
```

### 3. Build Index

```bash
# Use default config from .crawl_config.json
python scripts/build_index.py

# Override URL
python scripts/build_index.py --url https://dydx.exchange/blog/

# Use custom config file
python scripts/build_index.py --config /path/to/config.json

# Specify embedding model
python scripts/build_index.py --model BAAI/bge-m3

# Rebuild embeddings/chunks from existing HTML (recommended after parser/chunker changes)
python scripts/build_index.py --skip-crawl --rebuild

# Full recrawl + rebuild (when docs may have changed)
python scripts/build_index.py --rebuild
```

> **Note**: Recent bug fixes did not introduce new CLI parameters for `build_index.py`.

### 4. Start Agent

```bash
# TUI mode (recommended) — build then run
cd tui && pnpm build && node dist/index.js

# CLI fallback (no TUI)
python main.py
```

> **Behavior**: TUI bridge now starts first, and vectorstore/model initialization is lazy (triggered on first `rag_search`).
> If retrieval initialization/search fails, tool output uses `RAG_UNAVAILABLE`, and the assistant should report failure instead of answering from memory.
> Embedding load strategy is local-first: it prefers an existing HuggingFace cache snapshot (`local_files_only=True`) before trying remote download.

## .env Configuration

Copy `.env.example` to `.env` and configure:

```bash
# MiniMax API
ANTHROPIC_AUTH_TOKEN=your_token_here
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic

# Model
MODEL=MiniMax-M2.7

# Vectorstore
VECTORSTORE_DIR=./data/vectorstore

# Optional: runtime embedding model override
# Priority: EMBEDDING_MODEL > .crawl_config.json:model > BAAI/bge-m3
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Optional: retry cooldown (seconds) after lazy vectorstore init failure
VECTORSTORE_RETRY_INTERVAL_SEC=30
```

## Troubleshooting RAG_UNAVAILABLE

- Verify model priority first: `EMBEDDING_MODEL` in `.env` overrides `.crawl_config.json`.
- Keep index/runtime embedding models consistent to avoid vector dimension mismatch.
- For cached models, runtime now prefers local HF snapshot and does not require network.

## Anthropic SDK + MiniMax

MiniMax supports the standard Anthropic SDK:

```python
import anthropic

client = anthropic.Anthropic(
    api_key="your_token",
    base_url="https://api.minimax.io/anthropic",  # International
    # base_url="https://api.minimaxi.com/anthropic",  # China
)

response = client.messages.create(
    model="MiniMax-M2.7",
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Hello"}],
    tools=[...],
)
```

## Project Structure

```
prelude/
├── tui/                            # TypeScript TUI (pi-tui)
│   ├── src/index.ts                # Chat interface, spawns bridge as subprocess
│   ├── package.json                # pnpm, depends on @mariozechner/pi-tui
│   └── tsconfig.json
├── scripts/
│   └── build_index.py             # Index building script
├── crawlers/
│   └── gitbook_crawler.py         # Playwright crawler
├── parsers/
│   ├── html_to_markdown.py        # HTML -> Markdown
│   └── markdown_parser.py         # Markdown -> MarkdownBlock
├── chunkers/
│   └── semantic_chunker.py        # MarkdownBlock -> Document
├── embedders/
│   └── embedding_pipeline.py      # Document -> Chroma
├── agent/
│   ├── agent_loop.py              # Minimal Agent Loop (~500 lines)
│   ├── tools.py                   # Tool definitions + handlers
│   └── system_prompt.py           # System prompt
├── bridge/
│   └── pi_bridge.py               # JSONL bridge (spawned by TUI)
├── main.py                        # CLI fallback (no TUI)
├── pyproject.toml
├── uv.lock
├── .env.example
└── README.md
```

## Tech Stack

| Component | Tech |
|-----------|------|
| Python Env | uv |
| TUI | @mariozechner/pi-tui (TypeScript/pnpm) |
| Agent Loop | Custom (~500 lines), Anthropic SDK |
| LLM | MiniMax-M2.7 |
| Crawler | Playwright |
| Parser | Custom MarkdownBlock |
| Embedding | BGE-m3 |
| Vector DB | Chroma |

## Musical Movements Series

| Name | Meaning | Status |
|------|---------|--------|
| **prelude** | Opening | Current |
| **nocturne** | Night piece | Next |
| **sonata** | Sonata | Later |
| **symphony** | Symphony | Final |

## References

- [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) - Minimal Agent Loop reference
- [pi-mono](https://github.com/badlogic/pi-mono) - TUI reference
- [Anthropic SDK](https://docs.anthropic.com/) - Anthropic SDK docs
- [BGE-m3](https://huggingface.co/BAAI/bge-m3) - Embedding model
- [Chroma](https://github.com/chroma-core/chroma) - Vector DB
