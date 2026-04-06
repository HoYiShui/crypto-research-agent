"""
Analyze token length distribution for chunk documents.

This script is intentionally generic:
- Reads chunk artifacts (JSONL with page_content + metadata)
- Tokenizes each chunk with a chosen tokenizer/model
- Reports distribution, threshold counts, and longest samples

Example:
  uv run python scripts/analyze_chunks.py \
    --chunks data/chunks.jsonl \
    --model BAAI/bge-m3 \
    --threshold 512 --threshold 1024 --threshold 2048 \
    --top-n 20
"""

from __future__ import annotations

import argparse
import ast
import json
import statistics
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from rag.pipeline_config import get_embedding_config


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


def parse_heading_path(value: Any) -> str:
    if isinstance(value, list):
        return " > ".join(str(x) for x in value)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return ""
        try:
            parsed = ast.literal_eval(v)
            if isinstance(parsed, list):
                return " > ".join(str(x) for x in parsed)
        except Exception:
            pass
        return v
    return ""


def load_tokenizer(model: str):
    from transformers import AutoTokenizer

    local_snapshot = resolve_local_snapshot_path(model)
    if local_snapshot is not None:
        return AutoTokenizer.from_pretrained(str(local_snapshot), local_files_only=True), str(local_snapshot)

    return AutoTokenizer.from_pretrained(model), model


def percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    idx = int((len(sorted_values) - 1) * p)
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def analyze(chunks_path: Path, tokenizer) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with chunks_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            text = obj.get("page_content", "")
            meta = obj.get("metadata", {}) or {}

            token_count = len(tokenizer.encode(text, add_special_tokens=True, truncation=False))
            rows.append(
                {
                    "line": line_no,
                    "tokens": token_count,
                    "chars": len(text),
                    "chunk_id": meta.get("chunk_id", ""),
                    "source_url": meta.get("source_url", ""),
                    "heading_path": parse_heading_path(meta.get("heading_path")),
                    "chunk_type": meta.get("chunk_type", ""),
                    "preview": text[:140].replace("\n", " "),
                }
            )

    return rows


def main() -> None:
    embedding_cfg = get_embedding_config()
    default_model = str(embedding_cfg.get("model", "BAAI/bge-m3"))

    parser = argparse.ArgumentParser(description="Analyze token distribution of chunk artifacts")
    parser.add_argument("--chunks", type=str, default="data/chunks.jsonl", help="Path to chunks JSONL")
    parser.add_argument("--model", type=str, default=default_model, help="Tokenizer model id or local path")
    parser.add_argument("--threshold", action="append", type=int, default=[512, 1024, 2048, 4096], help="Token threshold (repeatable)")
    parser.add_argument("--top-n", type=int, default=15, help="Show top-N longest chunks")
    parser.add_argument("--json-out", type=str, default=None, help="Optional path to save JSON summary")
    args = parser.parse_args()

    chunks_path = Path(args.chunks)
    if not chunks_path.is_absolute():
        chunks_path = PROJECT_ROOT / chunks_path

    if not chunks_path.exists():
        raise SystemExit(f"chunks file not found: {chunks_path}")

    tokenizer, tokenizer_source = load_tokenizer(args.model)
    rows = analyze(chunks_path, tokenizer)
    if not rows:
        raise SystemExit("no chunks found")

    lengths = sorted(r["tokens"] for r in rows)

    summary = {
        "count": len(rows),
        "tokens_min": lengths[0],
        "tokens_p50": percentile(lengths, 0.50),
        "tokens_p90": percentile(lengths, 0.90),
        "tokens_p95": percentile(lengths, 0.95),
        "tokens_p99": percentile(lengths, 0.99),
        "tokens_max": lengths[-1],
        "tokens_mean": round(statistics.mean(lengths), 2),
        "tokenizer_source": tokenizer_source,
    }

    thresholds = sorted({int(t) for t in args.threshold if int(t) > 0})
    threshold_counts = {t: sum(1 for x in lengths if x > t) for t in thresholds}

    top_rows = sorted(rows, key=lambda x: x["tokens"], reverse=True)[: args.top_n]

    print("CHUNK_TOKEN_DISTRIBUTION")
    print(f"chunks: {summary['count']}")
    print(f"tokenizer: {summary['tokenizer_source']}")
    print(
        "tokens: "
        f"min={summary['tokens_min']} p50={summary['tokens_p50']} p90={summary['tokens_p90']} "
        f"p95={summary['tokens_p95']} p99={summary['tokens_p99']} max={summary['tokens_max']} "
        f"mean={summary['tokens_mean']}"
    )
    print("threshold_counts(>):")
    for t in thresholds:
        print(f"  >{t}: {threshold_counts[t]}")

    print(f"\nTOP_{args.top_n}_LONGEST")
    for r in top_rows:
        print("---")
        print(f"tokens={r['tokens']} chars={r['chars']} line={r['line']} chunk_id={r['chunk_id']}")
        print(f"type={r['chunk_type']}")
        print(f"source={r['source_url']}")
        print(f"heading={r['heading_path']}")
        print(f"preview={r['preview']}")

    if args.json_out:
        out_path = Path(args.json_out)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": summary,
            "threshold_counts": threshold_counts,
            "top_rows": top_rows,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\njson saved: {out_path}")


if __name__ == "__main__":
    main()
