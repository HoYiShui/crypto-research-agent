"""
build_index.py: Build RAG index entry point

Pipeline stages:
    1) crawl   -> raw_html/<site_name>/*.html
    2) parse   -> parsed_blocks.jsonl
    3) chunk   -> chunks.jsonl
    4) embed   -> vectorstore (embedding + storage)

Recommended usage:
    python scripts/build_index.py --rebuild

Selected usage examples:
    python scripts/build_index.py
    python scripts/build_index.py --from-stage parse --rebuild
    python scripts/build_index.py --from-stage chunk --rebuild
    python scripts/build_index.py --url https://dydx.exchange/blog/

Config schema (config/craw_list.json):
{
  "max_page": 50,
  "site": [
    {
      "name": "hyperliquid",
      "type": "gitbook",
      "base_url": "https://hyperliquid.gitbook.io/hyperliquid-docs/",
      "enable": true
    }
  ]
}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
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
from rag.pipeline_config import load_pipeline_config

STAGES = ("crawl", "parse", "chunk", "embed")
DEFAULT_CONFIG_PATH = project_root / "config" / "craw_list.json"
PIPELINE_CONFIG = load_pipeline_config()
DEFAULT_EMBEDDING_MODEL = str(PIPELINE_CONFIG.get("embedding", {}).get("model", "BAAI/bge-m3"))
DEFAULT_EMBED_BATCH_SIZE = int(PIPELINE_CONFIG.get("embedding", {}).get("batch_size", 4))
DEFAULT_EMBED_MAX_SEQ_LENGTH = int(PIPELINE_CONFIG.get("embedding", {}).get("max_seq_length", 1024))
DEFAULT_CHUNK_MAX_TOKENS = int(PIPELINE_CONFIG.get("chunking", {}).get("max_tokens_per_chunk", 1024))
DEFAULT_MAX_PAGE = int(PIPELINE_CONFIG.get("crawl", {}).get("default_max_page", 50))
SUPPORTED_SITE_TYPES = {"gitbook"}


@dataclass(frozen=True)
class CrawlSite:
    name: str
    type: str
    base_url: str
    enable: bool = True


@dataclass
class CachedDocument:
    """Lightweight cached document format for chunk artifacts."""

    page_content: str
    metadata: dict[str, Any]


def stage_index(stage: str) -> int:
    return STAGES.index(stage)


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load crawl source registry from JSON file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Config must be a JSON object: {path}")
            return data
    return {}


def url_to_slug(base_url: str) -> str:
    """Convert URL to a safe directory slug."""
    parsed = urlparse(base_url)
    slug = parsed.netloc + parsed.path
    slug = slug.strip("/").replace("/", "_")
    return re.sub(r"[^\w\-_]", "_", slug)


def _parse_positive_int(value: Any, field: str, default: int | None = None) -> int:
    if value is None:
        if default is None:
            raise ValueError(f"'{field}' is required")
        return default

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"'{field}' must be a positive integer")

    return value


def _parse_non_empty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field}' must be a non-empty string")
    return value.strip()


def _parse_site(item: Any, index: int) -> CrawlSite:
    if not isinstance(item, dict):
        raise ValueError(f"site[{index}] must be an object")

    name = _parse_non_empty_str(item.get("name"), f"site[{index}].name")
    site_type = _parse_non_empty_str(item.get("type"), f"site[{index}].type").lower()
    base_url = _parse_non_empty_str(item.get("base_url"), f"site[{index}].base_url")

    if site_type not in SUPPORTED_SITE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_SITE_TYPES))
        raise ValueError(f"site[{index}].type '{site_type}' is unsupported (supported: {supported})")

    enable_raw = item.get("enable", True)
    if not isinstance(enable_raw, bool):
        raise ValueError(f"site[{index}].enable must be boolean")

    return CrawlSite(name=name, type=site_type, base_url=base_url, enable=enable_raw)


def resolve_sources(
    config: dict[str, Any],
    url_override: str | None,
    max_pages_override: int | None,
) -> tuple[list[CrawlSite], int]:
    """Resolve crawl sources + max_page from config/CLI args."""
    max_page = _parse_positive_int(
        max_pages_override if max_pages_override is not None else config.get("max_page"),
        field="max_page",
        default=DEFAULT_MAX_PAGE,
    )

    if url_override:
        return [
            CrawlSite(
                name=url_to_slug(url_override) or "manual_site",
                type="gitbook",
                base_url=url_override,
                enable=True,
            )
        ], max_page

    raw_sites = config.get("site")
    if raw_sites is None:
        raise ValueError("No source configured. Set 'site' in config/craw_list.json or pass --url")
    if not isinstance(raw_sites, list):
        raise ValueError("'site' must be an array")

    parsed_sites = [_parse_site(item, index=i) for i, item in enumerate(raw_sites)]
    enabled_sites = [site for site in parsed_sites if site.enable]

    if not enabled_sites:
        raise ValueError("No enabled source. Set at least one site[].enable=true")

    return enabled_sites, max_page


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
    from rag.parsers.markdown_parser import MarkdownBlock

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
    from rag.parsers.markdown_parser import MarkdownBlock

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


def resolve_start_stage(from_stage: str | None) -> str:
    """Resolve stage to start from, defaults to crawl."""
    return from_stage or "crawl"


def cleanup_for_rebuild(
    start_stage: str,
    raw_html_root: Path,
    sites: list[CrawlSite],
    parsed_blocks_path: Path,
    chunks_path: Path,
    vectorstore_dir: Path,
) -> None:
    """Delete artifacts from start_stage onward."""
    if stage_index(start_stage) <= stage_index("crawl") and raw_html_root.exists():
        for site in sites:
            site_raw_dir = raw_html_root / site.name
            if site_raw_dir.exists():
                shutil.rmtree(site_raw_dir)

    if stage_index(start_stage) <= stage_index("parse") and parsed_blocks_path.exists():
        parsed_blocks_path.unlink()

    if stage_index(start_stage) <= stage_index("chunk") and chunks_path.exists():
        chunks_path.unlink()

    if stage_index(start_stage) <= stage_index("embed") and vectorstore_dir.exists():
        shutil.rmtree(vectorstore_dir)


def has_local_site_cache(site_raw_dir: Path) -> bool:
    """Quick check whether local raw HTML cache exists for a site."""
    return site_raw_dir.exists() and any(site_raw_dir.glob("*.html"))


async def _crawl_site(site: CrawlSite, output_dir: Path, max_pages: int) -> list[dict[str, Any]]:
    from rag.crawlers.gitbook_crawler import GitBookCrawler

    if site.type == "gitbook":
        crawler = GitBookCrawler(base_url=site.base_url, output_dir=str(output_dir))
        return await crawler.crawl(max_pages=max_pages)

    raise ValueError(f"Unsupported site type: {site.type}")


async def crawl_and_index(
    sites: list[CrawlSite],
    output_dir: str = "./data",
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    max_pages: int = DEFAULT_MAX_PAGE,
    chunk_max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS,
    embed_batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
    embed_max_seq_length: int = DEFAULT_EMBED_MAX_SEQ_LENGTH,
    rebuild: bool = False,
    from_stage: str | None = None,
):
    """Build index pipeline with resumable stages."""
    from rag.chunkers.semantic_chunker import blocks_to_documents
    from rag.embedders.embedding_pipeline import create_embedding_pipeline
    from rag.parsers.html_to_markdown import HTMLToMarkdownConverter
    from rag.parsers.markdown_parser import MarkdownParser

    start_stage = resolve_start_stage(from_stage=from_stage)

    output_root = Path(output_dir)
    raw_html_root = output_root / "raw_html"
    parsed_blocks_path = output_root / "parsed_blocks.jsonl"
    chunks_path = output_root / "chunks.jsonl"
    vectorstore_dir = output_root / "vectorstore"

    print(f"Pipeline start stage: {start_stage}")
    print(f"Enabled sites: {', '.join(site.name for site in sites)}")

    if rebuild:
        print("Rebuild mode: clearing artifacts from start stage onward...")
        cleanup_for_rebuild(
            start_stage=start_stage,
            raw_html_root=raw_html_root,
            sites=sites,
            parsed_blocks_path=parsed_blocks_path,
            chunks_path=chunks_path,
            vectorstore_dir=vectorstore_dir,
        )

    # Step 1/4: Crawl or load HTML
    pages: list[dict[str, Any]] = []
    failed_sites: list[str] = []

    if stage_index(start_stage) <= stage_index("crawl"):
        for site in sites:
            site_raw_dir = raw_html_root / site.name
            site_pages: list[dict[str, Any]]

            if not rebuild:
                if has_local_site_cache(site_raw_dir):
                    print(f"\n[Step 1/4] Found local cache for '{site.name}', skipping crawl")
                    site_pages = load_existing_html(site_raw_dir, base_url=site.base_url)
                    if site_pages:
                        print(f"  Loaded {len(site_pages)} HTML files from {site_raw_dir}")
                    else:
                        print(f"  [WARN] Cache exists but failed to load for '{site.name}', recrawling...")
                        site_pages = await _crawl_site(site=site, output_dir=site_raw_dir, max_pages=max_pages)
                else:
                    print(f"\n[Step 1/4] Crawling '{site.name}' from {site.base_url}...")
                    site_pages = await _crawl_site(site=site, output_dir=site_raw_dir, max_pages=max_pages)
            else:
                print(f"\n[Step 1/4] Crawling '{site.name}' from {site.base_url}...")
                site_pages = await _crawl_site(site=site, output_dir=site_raw_dir, max_pages=max_pages)

            if not site_pages:
                print(f"  [WARN] Crawling produced no pages for site '{site.name}', skipping.")
                failed_sites.append(site.name)
                continue

            for page in site_pages:
                page["site_name"] = site.name
                page["site_base_url"] = site.base_url
            pages.extend(site_pages)
    else:
        for site in sites:
            site_raw_dir = raw_html_root / site.name
            site_pages = load_existing_html(site_raw_dir, base_url=site.base_url)
            if not site_pages:
                print(f"  [WARN] No raw HTML cache for '{site.name}' in {site_raw_dir}, skipping.")
                failed_sites.append(site.name)
                continue
            for page in site_pages:
                page["site_name"] = site.name
                page["site_base_url"] = site.base_url
            pages.extend(site_pages)

        print(f"\n[Step 1/4] Loaded {len(pages)} HTML files from disk")

    if failed_sites:
        print(f"[WARN] Step 1 skipped failed sites: {', '.join(failed_sites)}")

    if not pages:
        print("Error: no pages available after Step 1. Use --rebuild, --url, or fix site availability.")
        sys.exit(1)

    print(f"Crawl/Load complete: {len(pages)} pages")

    # Step 2/4: Parse or load parsed blocks
    if stage_index(start_stage) <= stage_index("parse"):
        print("\n[Step 2/4] Parsing...")
        converter = HTMLToMarkdownConverter()
        parser = MarkdownParser()

        all_blocks = []
        for page in pages:
            markdown_text = converter.convert(page["html"], base_url=page["url"])
            blocks = parser.parse(markdown_text)

            for block in blocks:
                block.source_url = _absolutize_url(page["url"], base_url=page.get("site_base_url", ""))

            all_blocks.extend(blocks)
            site_name = page.get("site_name", "unknown")
            print(f"  [{site_name}] {page['title'][:50]}: {len(blocks)} blocks")

        save_blocks(all_blocks, parsed_blocks_path)
        print(f"Parse complete: {len(all_blocks)} blocks total")
        print(f"Parsed cache: {parsed_blocks_path}")
    else:
        print("\n[Step 2/4] Loading parsed blocks cache...")
        all_blocks = load_blocks(parsed_blocks_path)
        print(f"Parse cache loaded: {len(all_blocks)} blocks")

    # Step 3/4: Chunk or load chunks
    if stage_index(start_stage) <= stage_index("chunk"):
        print("\n[Step 3/4] Chunking...")
        documents = blocks_to_documents(all_blocks, max_tokens_per_chunk=chunk_max_tokens)
        save_documents(documents, chunks_path)
        print(f"Chunking complete: {len(documents)} chunks")
        print(f"Chunk cache: {chunks_path}")
    else:
        print("\n[Step 3/4] Loading chunk cache...")
        documents = load_documents(chunks_path)
        print(f"Chunk cache loaded: {len(documents)} chunks")

    # Step 4/4: Embed + Store
    if not rebuild and vectorstore_has_data(str(vectorstore_dir)):
        print("\n[Step 4/4] Vectorstore already has data, skipping embed (use --rebuild to overwrite)")
    else:
        print("\n[Step 4/4] Embedding + Storing...")
        pipeline = create_embedding_pipeline(
            model_name=model_name,
            persist_dir=str(vectorstore_dir),
            batch_size=embed_batch_size,
            max_seq_length=embed_max_seq_length,
        )
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
        help="Path to source registry JSON (default: config/craw_list.json)",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Single URL override (as one enabled gitbook site)",
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
        help="Embedding model name override",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages to crawl for each enabled site (overrides config.max_page)",
    )
    parser.add_argument(
        "--chunk-max-tokens",
        type=int,
        default=None,
        help="Chunk token budget override (default from config/rag_pipeline.yaml)",
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

    try:
        config = load_config(args.config)
        sites, max_pages = resolve_sources(
            config=config,
            url_override=args.url,
            max_pages_override=args.max_pages,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if args.rebuild and not args.url and len(sites) > 1:
        print("[WARN] --rebuild without --url will recrawl all enabled sites from config.")

    if args.chunk_max_tokens is not None and args.chunk_max_tokens <= 0:
        print("Error: --chunk-max-tokens must be a positive integer")
        sys.exit(1)

    pipeline_cfg = load_pipeline_config()
    chunk_cfg = pipeline_cfg.get("chunking", {})
    embed_cfg = pipeline_cfg.get("embedding", {})

    model_name = args.model or DEFAULT_EMBEDDING_MODEL
    chunk_max_tokens = args.chunk_max_tokens or int(chunk_cfg.get("max_tokens_per_chunk", DEFAULT_CHUNK_MAX_TOKENS))
    embed_batch_size = int(embed_cfg.get("batch_size", DEFAULT_EMBED_BATCH_SIZE))
    embed_max_seq_length = int(embed_cfg.get("max_seq_length", DEFAULT_EMBED_MAX_SEQ_LENGTH))

    asyncio.run(
        crawl_and_index(
            sites=sites,
            output_dir=args.output,
            model_name=model_name,
            max_pages=max_pages,
            chunk_max_tokens=chunk_max_tokens,
            embed_batch_size=embed_batch_size,
            embed_max_seq_length=embed_max_seq_length,
            rebuild=args.rebuild,
            from_stage=args.from_stage,
        )
    )


if __name__ == "__main__":
    main()
