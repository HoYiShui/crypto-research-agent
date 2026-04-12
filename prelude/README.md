# Prelude

> Crypto research agent series - RAG + Minimal Agent experimental playground

[English](README.md) | [中文](README_zh.md)

Initial milestone in the Crypto Research Agent series, focused on validating core RAG and minimal agent capabilities.

## Documentation

- Local docs index: `prelude/docs/README.md`
- RAG workflow: `prelude/docs/rag/rag_workflow.md`
- Incident log: `prelude/docs/research/rag-pipeline-incident-log.md`
- Execution plans: `prelude/docs/exec-plans/`

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
# Recommended: rebuild index end-to-end from your configured source
python scripts/build_index.py --rebuild
```

> **Note**: For advanced or recovery workflows, see the top docstring in `scripts/build_index.py` (or run `python scripts/build_index.py --help`).
> Source registry schema is documented in `config/README.md`.

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
# Default runtime embedding model is BAAI/bge-m3
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Optional: retry cooldown (seconds) after lazy vectorstore init failure
VECTORSTORE_RETRY_INTERVAL_SEC=30
```

## Troubleshooting RAG_UNAVAILABLE

- Verify model setting first: `EMBEDDING_MODEL` in `.env` overrides the runtime default (`BAAI/bge-m3`).
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
├── app/                            # Runtime app layer
│   ├── agent/                      # Minimal agent loop + tools
│   └── bridge/                     # JSONL bridge (spawned by TUI)
├── rag/                            # RAG pipeline layer
│   ├── crawlers/                   # Crawl HTML
│   ├── parsers/                    # HTML/Markdown parsing
│   ├── chunkers/                   # Semantic chunking
│   └── embedders/                  # Embedding + vectorstore
├── config/
│   ├── craw_list.yaml              # Crawl source registry
│   └── rag_pipeline.yaml           # RAG pipeline defaults
├── data/                           # Pipeline artifacts and vectorstore
├── scripts/
│   ├── build_index.py              # Index building script
│   ├── analyze_chunks.py           # Generic chunk token distribution analysis
│   └── investigate_chunk_outliers.py # OOM-oriented chunk outlier investigation
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

## Crypto Research Agent Series

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
