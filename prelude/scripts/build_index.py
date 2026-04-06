"""
build_index.py: Build RAG index entry point

Pipeline stages:
    1) crawl   -> raw_html/*.html
    2) parse   -> parsed_blocks.jsonl
    3) chunk   -> chunks.jsonl
    4) embed   -> vectorstore (embedding + storage)

Usage examples:
    python scripts/build_index.py
    python scripts/build_index.py --url https://dydx.exchange/blog/
    python scripts/build_index.py --skip-crawl --rebuild
    python scripts/build_index.py --skip-parse --rebuild
    python scripts/build_index.py --from-stage chunk --rebuild
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv

load_dotenv()

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DEFAULT_CONFIG_PATH = project_root / ".crawl_config.json"
STAGES = ("crawl", "parse", "chunk", "embed")


@dataclass
class CachedDocument:
    """Lightweight cached document format for chunk artifacts."""

    page_content: str
    metadata: dict[str, Any]


def stage_index(stage: str) -> int:
    return STAGES.index(stage)


def load_config(config_path: str | None = None) -> dict:
    """Load crawl config from JSON file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def url_to_slug(base_url: str) -> str:
    """Convert URL to a safe directory slug."""
    parsed = urlparse(base_url)
    slug = parsed.netloc + parsed.path
    slug = slug.strip("/").replace("/", "_")
    import re

    return re.sub(r"[^\w\-_]", "_", slug)


def _absolutize_url(url: str, base_url: str = "") -> str:
    """Return absolute URL when possible."""
    if not url:
        return ""

    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url

    if base_url:
        return urljoin(base_url, url)

    return url


def _extract_source_url_from_html(html: str, fallback_url: str = "") -> str:
    """Best-effort extraction of canonical source URL from HTML."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return fallback_url

    try:
        soup = BeautifulSoup(html, "html.parser")

        canonical = soup.find("link", attrs={"rel": "canonical"})
        if canonical and canonical.get("href"):
            return _absolutize_url(canonical["href"].strip(), base_url=fallback_url)

        og_url = soup.find("meta", attrs={"property": "og:url"})
        if og_url and og_url.get("content"):
            return _absolutize_url(og_url["content"].strip(), base_url=fallback_url)
    except Exception:
        pass

    return fallback_url


def load_existing_html(raw_html_dir: Path, base_url: str = "") -> list[dict[str, Any]]:
    """Load pages from existing HTML files on disk."""
    if not raw_html_dir.exists():
        return []

    pages: list[dict[str, Any]] = []
    html_files = sorted(raw_html_dir.glob("*.html"))

    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")

        # URL slug filename -> readable path
        title = html_file.stem.replace("_", "/").replace("+", " ")

        if title == "index":
            fallback_url = base_url or title
        elif base_url:
            fallback_url = f"{base_url.rstrip('/')}/{title.lstrip('/')}"
        else:
            fallback_url = title

        source_url = _extract_source_url_from_html(content, fallback_url=fallback_url)
        source_url = _absolutize_url(source_url, base_url=base_url)

        pages.append(
            {
                "url": source_url,
                "title": title,
                "html": content,
                "filename": html_file.name,
            }
        )

    return pages


def vectorstore_has_data(persist_dir: str) -> bool:
    """Check if vectorstore already has documents (no model loading needed)."""
    persist_path = Path(persist_dir)
    if not persist_path.exists():
        return False
    return (persist_path / "chroma.sqlite3").exists() or any(persist_path.glob("**/*.bin"))


def _serialize_block_item(item: Any) -> Any:
    from parsers.markdown_parser import MarkdownBlock

    if isinstance(item, MarkdownBlock):
        return {"__markdown_block__": _serialize_block(item)}
    return item


def _deserialize_block_item(item: Any) -> Any:
    if isinstance(item, dict) and "__markdown_block__" in item:
        return _deserialize_block(item["__markdown_block__"])
    return item


def _serialize_block(block: Any) -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "heading_path": block.heading_path,
        "heading_level": block.heading_level,
        "block_type": block.block_type,
        "content": block.content,
        "items": [_serialize_block_item(i) for i in (block.items or [])],
        "table_headers": block.table_headers,
        "table_rows": block.table_rows,
        "code": block.code,
        "code_lang": block.code_lang,
        "source_url": block.source_url,
        "raw_markdown": block.raw_markdown,
    }


def _deserialize_block(data: dict[str, Any]):
    from parsers.markdown_parser import MarkdownBlock

    return MarkdownBlock(
        block_id=data.get("block_id", ""),
        heading_path=data.get("heading_path") or [],
        heading_level=data.get("heading_level", 1),
        block_type=data.get("block_type", "text"),
        content=data.get("content"),
        items=[_deserialize_block_item(i) for i in (data.get("items") or [])],
        table_headers=data.get("table_headers"),
        table_rows=data.get("table_rows"),
        code=data.get("code"),
        code_lang=data.get("code_lang"),
        source_url=data.get("source_url"),
        raw_markdown=data.get("raw_markdown"),
    )


def save_blocks(blocks: list[Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for block in blocks:
            f.write(json.dumps(_serialize_block(block), ensure_ascii=False) + "\n")


def load_blocks(in_path: Path) -> list[Any]:
    if not in_path.exists():
        raise FileNotFoundError(f"Parsed blocks cache not found: {in_path}")

    blocks = []
    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            blocks.append(_deserialize_block(json.loads(line)))
    return blocks


def save_documents(documents: list[Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for doc in documents:
            payload = {
                "page_content": doc.page_content,
                "metadata": doc.metadata,
            }
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_documents(in_path: Path) -> list[CachedDocument]:
    if not in_path.exists():
        raise FileNotFoundError(f"Chunk cache not found: {in_path}")

    docs: list[CachedDocument] = []
    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            docs.append(
                CachedDocument(
                    page_content=payload.get("page_content", ""),
                    metadata=payload.get("metadata", {}),
                )
            )
    return docs


def resolve_start_stage(skip_crawl: bool, skip_parse: bool, from_stage: str | None) -> str:
    """
    Resolve stage to start from.

    Priority:
      from_stage > skip_parse > skip_crawl > crawl
    """
    if from_stage:
        return from_stage

    if skip_parse:
        return "chunk"

    if skip_crawl:
        return "parse"

    return "crawl"


def cleanup_for_rebuild(
    start_stage: str,
    raw_html_dir: Path,
    parsed_blocks_path: Path,
    chunks_path: Path,
    vectorstore_dir: Path,
) -> None:
    """Delete artifacts from start_stage onward."""
    if stage_index(start_stage) <= stage_index("crawl") and raw_html_dir.exists():
        shutil.rmtree(raw_html_dir)

    if stage_index(start_stage) <= stage_index("parse") and parsed_blocks_path.exists():
        parsed_blocks_path.unlink()

    if stage_index(start_stage) <= stage_index("chunk") and chunks_path.exists():
        chunks_path.unlink()

    if stage_index(start_stage) <= stage_index("embed") and vectorstore_dir.exists():
        shutil.rmtree(vectorstore_dir)


async def crawl_and_index(
    base_url: str,
    output_dir: str = "./data",
    model_name: str = "BAAI/bge-m3",
    max_pages: int = 50,
    skip_crawl: bool = False,
    skip_parse: bool = False,
    rebuild: bool = False,
    from_stage: str | None = None,
):
    """Build index pipeline with resumable stages."""
    from crawlers.gitbook_crawler import GitBookCrawler
    from parsers.html_to_markdown import HTMLToMarkdownConverter
    from parsers.markdown_parser import MarkdownParser
    from chunkers.semantic_chunker import blocks_to_documents
    from embedders.embedding_pipeline import create_embedding_pipeline

    start_stage = resolve_start_stage(
        skip_crawl=skip_crawl,
        skip_parse=skip_parse,
        from_stage=from_stage,
    )

    output_root = Path(output_dir)
    raw_html_dir = output_root / "raw_html"
    parsed_blocks_path = output_root / "parsed_blocks.jsonl"
    chunks_path = output_root / "chunks.jsonl"
    vectorstore_dir = output_root / "vectorstore"

    print(f"Pipeline start stage: {start_stage}")

    if rebuild:
        print("Rebuild mode: clearing artifacts from start stage onward...")
        cleanup_for_rebuild(
            start_stage=start_stage,
            raw_html_dir=raw_html_dir,
            parsed_blocks_path=parsed_blocks_path,
            chunks_path=chunks_path,
            vectorstore_dir=vectorstore_dir,
        )

    # ── Step 1/4: Crawl or load HTML ──────────────────────────────────────────
    pages: list[dict[str, Any]]

    if stage_index(start_stage) <= stage_index("crawl"):
        if not rebuild:
            existing = load_existing_html(raw_html_dir, base_url=base_url)
            if existing:
                print(f"\n[Step 1/4] Loading {len(existing)} existing HTML files from disk (skip crawl)")
                pages = existing
            else:
                print(f"\n[Step 1/4] Crawling from {base_url}...")
                crawler = GitBookCrawler(base_url=base_url, output_dir=str(raw_html_dir))
                pages = await crawler.crawl(max_pages=max_pages)
        else:
            print(f"\n[Step 1/4] Crawling from {base_url}...")
            crawler = GitBookCrawler(base_url=base_url, output_dir=str(raw_html_dir))
            pages = await crawler.crawl(max_pages=max_pages)

        if not pages:
            print("Error: crawling produced no pages.")
            sys.exit(1)
    else:
        pages = load_existing_html(raw_html_dir, base_url=base_url)
        if not pages:
            print("Error: no raw HTML cache found. Run with crawl stage first.")
            sys.exit(1)
        print(f"\n[Step 1/4] Loaded {len(pages)} HTML files from disk")

    print(f"Crawl/Load complete: {len(pages)} pages")

    # ── Step 2/4: Parse or load parsed blocks ────────────────────────────────
    if stage_index(start_stage) <= stage_index("parse"):
        print("\n[Step 2/4] Parsing...")
        converter = HTMLToMarkdownConverter()
        parser = MarkdownParser()

        all_blocks = []
        for page in pages:
            markdown_text = converter.convert(page["html"], base_url=page["url"])
            blocks = parser.parse(markdown_text)

            for block in blocks:
                block.source_url = _absolutize_url(page["url"], base_url=base_url)

            all_blocks.extend(blocks)
            print(f"  {page['title'][:50]}: {len(blocks)} blocks")

        save_blocks(all_blocks, parsed_blocks_path)
        print(f"Parse complete: {len(all_blocks)} blocks total")
        print(f"Parsed cache: {parsed_blocks_path}")
    else:
        print("\n[Step 2/4] Loading parsed blocks cache...")
        all_blocks = load_blocks(parsed_blocks_path)
        print(f"Parse cache loaded: {len(all_blocks)} blocks")

    # ── Step 3/4: Chunk or load chunks ───────────────────────────────────────
    if stage_index(start_stage) <= stage_index("chunk"):
        print("\n[Step 3/4] Chunking...")
        documents = blocks_to_documents(all_blocks)
        save_documents(documents, chunks_path)
        print(f"Chunking complete: {len(documents)} chunks")
        print(f"Chunk cache: {chunks_path}")
    else:
        print("\n[Step 3/4] Loading chunk cache...")
        documents = load_documents(chunks_path)
        print(f"Chunk cache loaded: {len(documents)} chunks")

    # ── Step 4/4: Embed + Store ───────────────────────────────────────────────
    if not rebuild and vectorstore_has_data(str(vectorstore_dir)):
        print("\n[Step 4/4] Vectorstore already has data, skipping embed (use --rebuild to overwrite)")
    else:
        print("\n[Step 4/4] Embedding + Storing...")
        pipeline = create_embedding_pipeline(model_name=model_name, persist_dir=str(vectorstore_dir))
        pipeline.add_documents(documents)
        print(f"Storage complete: {len(documents)} documents")

    print("\n[OK] Index ready!")
    print(f"   Data dir: {output_dir}")
    print(f"   Parsed cache: {parsed_blocks_path}")
    print(f"   Chunk cache: {chunks_path}")
    print(f"   Vectorstore: {vectorstore_dir}")


def main():
    parser = argparse.ArgumentParser(description="Build RAG index")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: .crawl_config.json)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="GitBook URL to crawl (overrides config)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./data",
        help="Output directory",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Embedding model name (overrides config)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages to crawl (overrides config)",
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip crawling, use existing HTML cache (parse+chunk+embed).",
    )
    parser.add_argument(
        "--skip-parse",
        action="store_true",
        help="Skip crawling and parsing, start from chunk stage using parsed_blocks.jsonl.",
    )
    parser.add_argument(
        "--from-stage",
        type=str,
        choices=STAGES,
        default=None,
        help="Explicitly choose pipeline start stage: crawl|parse|chunk|embed.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete artifacts from the chosen start stage onward, then rebuild.",
    )

    args = parser.parse_args()

    config = load_config(args.config)

    base_url = args.url or config.get("base_url")
    max_pages = args.max_pages or config.get("max_pages", 50)
    model_name = args.model or config.get("model", "BAAI/bge-m3")

    if not base_url:
        print("Error: No URL specified. Use --url or set base_url in .crawl_config.json")
        sys.exit(1)

    if args.skip_parse and args.from_stage and args.from_stage not in {"chunk", "embed"}:
        print("Error: --skip-parse conflicts with --from-stage crawl|parse")
        sys.exit(1)

    asyncio.run(
        crawl_and_index(
            base_url=base_url,
            output_dir=args.output,
            model_name=model_name,
            max_pages=max_pages,
            skip_crawl=args.skip_crawl,
            skip_parse=args.skip_parse,
            rebuild=args.rebuild,
            from_stage=args.from_stage,
        )
    )


if __name__ == "__main__":
    main()
