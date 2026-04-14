"""
Investigate oversized chunks and potential embedding OOM risks.

This script is intentionally issue-focused (unlike analyze_chunks.py):
- Computes model-token lengths for chunks
- Estimates attention buffer usage under given B/H/dtype assumptions
- Flags risky chunks under memory budget
- Maps risky chunks back to candidate parsed MarkdownBlocks

Example:
  uv run python scripts/investigate_chunk_outliers.py \
    --chunks data/chunks.jsonl \
    --parsed-blocks data/parsed_blocks.jsonl \
    --model BAAI/bge-m3 \
    --batch-size 32 --memory-gib 8 --top-n 20 \
    --json-out data/reports/chunk_outlier_investigation.json
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rag.parsers.markdown_parser import MarkdownBlock, block_to_embedding_text
from rag.pipeline_config import get_chunking_config, get_embedding_config


def parse_heading_path(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(x) for x in value if str(x).strip())
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return tuple()
        try:
            parsed = ast.literal_eval(v)
            if isinstance(parsed, list):
                return tuple(str(x) for x in parsed if str(x).strip())
        except Exception:
            pass
        return (v,)
    return tuple()


def resolve_local_snapshot_path(model_name: str) -> Path | None:
    if "/" not in model_name:
        p = Path(model_name)
        return p if p.exists() else None

    repo_dir = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{model_name.replace('/', '--')}"
    snapshots = repo_dir / "snapshots"
    refs_main = repo_dir / "refs" / "main"

    if not snapshots.exists():
        return None

    if refs_main.exists():
        rev = refs_main.read_text(encoding="utf-8").strip()
        p = snapshots / rev
        if p.exists():
            return p

    cands = [p for p in snapshots.iterdir() if p.is_dir()]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def load_tokenizer(model: str):
    from transformers import AutoTokenizer

    local_snapshot = resolve_local_snapshot_path(model)
    if local_snapshot is not None:
        return AutoTokenizer.from_pretrained(str(local_snapshot), local_files_only=True), str(local_snapshot)

    return AutoTokenizer.from_pretrained(model), model


def load_tiktoken_encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def attention_buffer_gib(length_tokens: int, batch_size: int, heads: int, dtype_bytes: int) -> float:
    if length_tokens <= 0:
        return 0.0
    raw_bytes = batch_size * heads * (length_tokens**2) * dtype_bytes
    return raw_bytes / (1024**3)


def length_budget(memory_gib: float, batch_size: int, heads: int, dtype_bytes: int) -> int:
    if memory_gib <= 0:
        return 0
    raw_bytes = memory_gib * (1024**3)
    denom = batch_size * heads * dtype_bytes
    if denom <= 0:
        return 0
    return int(math.sqrt(raw_bytes / denom))


def load_chunks(chunks_path: Path, tokenizer, tiktoken_encoder) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with chunks_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            text = obj.get("page_content", "")
            meta = obj.get("metadata", {}) or {}

            model_tokens = len(tokenizer.encode(text, add_special_tokens=True, truncation=False))
            if tiktoken_encoder is not None:
                estimator_tokens = len(tiktoken_encoder.encode(text))
            else:
                estimator_tokens = len(text) // 4

            heading = parse_heading_path(meta.get("heading_path"))
            rows.append(
                {
                    "line": line_no,
                    "chunk_id": meta.get("chunk_id", ""),
                    "source_url": meta.get("source_url", ""),
                    "heading_path": heading,
                    "chunk_type": meta.get("chunk_type", ""),
                    "heading_level": meta.get("heading_level", 0),
                    "text": text,
                    "chars": len(text),
                    "model_tokens": model_tokens,
                    "estimator_tokens": estimator_tokens,
                }
            )

    return rows


def _make_block_from_obj(obj: dict[str, Any]) -> MarkdownBlock:
    return MarkdownBlock(
        block_id=str(obj.get("block_id", "")),
        heading_path=obj.get("heading_path") or [],
        heading_level=int(obj.get("heading_level") or 1),
        block_type=str(obj.get("block_type") or "text"),
        content=obj.get("content"),
        items=obj.get("items") or [],
        table_headers=obj.get("table_headers"),
        table_rows=obj.get("table_rows"),
        code=obj.get("code"),
        code_lang=obj.get("code_lang"),
        source_url=obj.get("source_url"),
        raw_markdown=obj.get("raw_markdown"),
    )


def load_block_index(parsed_blocks_path: Path, tokenizer) -> dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]]:
    block_index: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}

    with parsed_blocks_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            block = _make_block_from_obj(obj)
            source_url = block.source_url or ""
            heading_path = tuple(str(x) for x in (block.heading_path or []) if str(x).strip())
            key = (source_url, heading_path)

            emb_text = block_to_embedding_text(block)
            token_count = len(tokenizer.encode(emb_text, add_special_tokens=True, truncation=False))
            block_index.setdefault(key, []).append(
                {
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "heading_level": block.heading_level,
                    "source_url": source_url,
                    "heading_path": heading_path,
                    "embedding_text": emb_text,
                    "model_tokens": token_count,
                    "chars": len(emb_text),
                    "raw_preview": (block.raw_markdown or "")[:140].replace("\n", " "),
                }
            )

    return block_index


def detect_nav_like(text: str) -> bool:
    if not text:
        return False
    snippet = text[:2400].lower()
    patterns = [
        "powered by gitbook",
        "chevron-right",
        "search",
        "technical docs",
        "official links",
    ]
    return any(p in snippet for p in patterns)


def summarize_groups(
    chunks: list[dict[str, Any]],
    block_index: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]],
    max_tokens_cfg: int,
    memory_budget_tokens: int,
    batch_size: int,
    heads: int,
    dtype_bytes: int,
    top_n: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    risky: list[dict[str, Any]] = []

    for row in chunks:
        model_tokens = row["model_tokens"]
        key = (row["source_url"], row["heading_path"])
        candidates = block_index.get(key, [])

        by_type: dict[str, int] = {}
        for b in candidates:
            by_type[b["block_type"]] = by_type.get(b["block_type"], 0) + 1

        top_blocks = sorted(candidates, key=lambda x: x["model_tokens"], reverse=True)[:3]
        matched_blocks = 0
        for b in candidates:
            emb = b.get("embedding_text", "")
            if emb and emb in row["text"]:
                matched_blocks += 1

        attn_gib = attention_buffer_gib(
            length_tokens=model_tokens,
            batch_size=batch_size,
            heads=heads,
            dtype_bytes=dtype_bytes,
        )

        ratio = round(model_tokens / max(1, row["estimator_tokens"]), 3)
        item = {
            "line": row["line"],
            "chunk_id": row["chunk_id"],
            "source_url": row["source_url"],
            "heading_path": " > ".join(row["heading_path"]),
            "chunk_type": row["chunk_type"],
            "model_tokens": model_tokens,
            "estimator_tokens": row["estimator_tokens"],
            "model_vs_estimator_ratio": ratio,
            "chars": row["chars"],
            "estimated_attention_gib": round(attn_gib, 2),
            "risk_vs_budget": model_tokens >= memory_budget_tokens,
            "over_chunk_max": model_tokens > max_tokens_cfg,
            "empty_heading_path": len(row["heading_path"]) == 0,
            "nav_like_text": detect_nav_like(row["text"]),
            "candidate_block_count": len(candidates),
            "candidate_block_type_counts": by_type,
            "candidate_matched_block_count": matched_blocks,
            "candidate_top_blocks": [
                {
                    "block_id": b["block_id"],
                    "block_type": b["block_type"],
                    "model_tokens": b["model_tokens"],
                    "chars": b["chars"],
                    "raw_preview": b["raw_preview"],
                }
                for b in top_blocks
            ],
            "text_preview": row["text"][:200].replace("\n", " "),
        }

        if model_tokens >= memory_budget_tokens or model_tokens > max_tokens_cfg:
            risky.append(item)

    risky.sort(key=lambda x: x["model_tokens"], reverse=True)

    lengths = sorted(x["model_tokens"] for x in chunks)
    summary = {
        "chunk_count": len(chunks),
        "tokens_min": lengths[0] if lengths else 0,
        "tokens_p50": lengths[int((len(lengths) - 1) * 0.50)] if lengths else 0,
        "tokens_p90": lengths[int((len(lengths) - 1) * 0.90)] if lengths else 0,
        "tokens_p95": lengths[int((len(lengths) - 1) * 0.95)] if lengths else 0,
        "tokens_p99": lengths[int((len(lengths) - 1) * 0.99)] if lengths else 0,
        "tokens_max": lengths[-1] if lengths else 0,
        "tokens_mean": round(statistics.mean(lengths), 2) if lengths else 0,
        "over_chunk_max_count": sum(1 for x in chunks if x["model_tokens"] > max_tokens_cfg),
        "over_memory_budget_count": sum(1 for x in chunks if x["model_tokens"] >= memory_budget_tokens),
        "nav_like_count": sum(1 for x in chunks if detect_nav_like(x["text"])),
        "empty_heading_count": sum(1 for x in chunks if len(x["heading_path"]) == 0),
        "top_risky": risky[:top_n],
    }

    return risky, summary


def main() -> None:
    embedding_cfg = get_embedding_config()
    chunk_cfg = get_chunking_config()

    parser = argparse.ArgumentParser(description="Investigate oversized chunk outliers and OOM risk")
    parser.add_argument("--chunks", type=str, default="data/chunks.jsonl", help="Path to chunks JSONL")
    parser.add_argument("--parsed-blocks", type=str, default="data/parsed_blocks.jsonl", help="Path to parsed blocks JSONL")
    parser.add_argument("--model", type=str, default=str(embedding_cfg.get("model", "BAAI/bge-m3")), help="Tokenizer model id or local path")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size for risk estimation")
    parser.add_argument("--heads", type=int, default=16, help="Attention heads (bge-m3 default 16)")
    parser.add_argument("--dtype-bytes", type=int, default=4, help="Bytes per attention element (fp32=4)")
    parser.add_argument("--memory-gib", type=float, default=8.0, help="Memory budget GiB for single attention buffer")
    parser.add_argument("--max-chunk-tokens", type=int, default=int(chunk_cfg.get("max_tokens_per_chunk", 1024)), help="Configured chunk max tokens")
    parser.add_argument("--top-n", type=int, default=20, help="Show top-N risky chunks")
    parser.add_argument("--json-out", type=str, default=None, help="Optional output JSON file")
    args = parser.parse_args()

    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path
    parsed_blocks_path = Path(args.parsed_blocks)
    if not parsed_blocks_path.is_absolute():
        parsed_blocks_path = PROJECT_ROOT / parsed_blocks_path

    if not chunks_path.exists():
        raise SystemExit(f"chunks file not found: {chunks_path}")
    if not parsed_blocks_path.exists():
        raise SystemExit(f"parsed blocks file not found: {parsed_blocks_path}")

    tokenizer, tokenizer_source = load_tokenizer(args.model)
    tiktoken_encoder = load_tiktoken_encoder()

    chunks = load_chunks(chunks_path, tokenizer, tiktoken_encoder)
    block_index = load_block_index(parsed_blocks_path, tokenizer)

    budget_tokens = length_budget(
        memory_gib=args.memory_gib,
        batch_size=args.batch_size,
        heads=args.heads,
        dtype_bytes=args.dtype_bytes,
    )

    risky, summary = summarize_groups(
        chunks=chunks,
        block_index=block_index,
        max_tokens_cfg=args.max_chunk_tokens,
        memory_budget_tokens=budget_tokens,
        batch_size=args.batch_size,
        heads=args.heads,
        dtype_bytes=args.dtype_bytes,
        top_n=args.top_n,
    )

    print("CHUNK_OUTLIER_INVESTIGATION")
    print(f"tokenizer: {tokenizer_source}")
    print(
        "risk_assumption: "
        f"batch={args.batch_size}, heads={args.heads}, dtype_bytes={args.dtype_bytes}, memory_gib={args.memory_gib}"
    )
    print(f"derived_token_budget_L: {budget_tokens}")
    print(
        "distribution: "
        f"count={summary['chunk_count']} min={summary['tokens_min']} p50={summary['tokens_p50']} "
        f"p90={summary['tokens_p90']} p95={summary['tokens_p95']} p99={summary['tokens_p99']} "
        f"max={summary['tokens_max']} mean={summary['tokens_mean']}"
    )
    print(
        "counts: "
        f"over_chunk_max={summary['over_chunk_max_count']} "
        f"over_memory_budget={summary['over_memory_budget_count']} "
        f"empty_heading={summary['empty_heading_count']} nav_like={summary['nav_like_count']}"
    )

    print(f"\nTOP_{args.top_n}_RISKY")
    for item in summary["top_risky"]:
        print("---")
        print(
            f"tokens={item['model_tokens']} est_tokens={item['estimator_tokens']} "
            f"ratio={item['model_vs_estimator_ratio']} attn_gib~{item['estimated_attention_gib']}"
        )
        print(
            f"chunk_id={item['chunk_id']} line={item['line']} type={item['chunk_type']} "
            f"over_max={item['over_chunk_max']} over_budget={item['risk_vs_budget']}"
        )
        print(f"source={item['source_url']}")
        print(f"heading={item['heading_path'] or '<empty>'}")
        print(
            "candidates="
            f"{item['candidate_block_count']} matched={item['candidate_matched_block_count']} "
            f"types={item['candidate_block_type_counts']}"
        )
        print(
            f"flags: empty_heading={item['empty_heading_path']} nav_like={item['nav_like_text']}"
        )
        print(f"preview={item['text_preview']}")

    if args.json_out:
        out_path = Path(args.json_out)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "assumptions": {
                "batch_size": args.batch_size,
                "heads": args.heads,
                "dtype_bytes": args.dtype_bytes,
                "memory_gib": args.memory_gib,
                "derived_token_budget_L": budget_tokens,
                "max_chunk_tokens": args.max_chunk_tokens,
                "model": args.model,
                "tokenizer_source": tokenizer_source,
            },
            "summary": {k: v for k, v in summary.items() if k != "top_risky"},
            "top_risky": summary["top_risky"],
            "risky_count": len(risky),
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\njson saved: {out_path}")


if __name__ == "__main__":
    main()
