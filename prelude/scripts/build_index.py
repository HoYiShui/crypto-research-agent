"""
build_index.py: Build RAG index entry point

Usage:
    python scripts/build_index.py                    # Use .crawl_config.json
    python scripts/build_index.py --url <url>       # Override URL
    python scripts/build_index.py --config <path>  # Use custom config
    python scripts/build_index.py --rebuild         # Force full rebuild
    python scripts/build_index.py --skip-crawl      # Skip crawl (use existing HTML)
"""
import asyncio
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
import sys

load_dotenv()

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DEFAULT_CONFIG_PATH = project_root / ".crawl_config.json"


def load_config(config_path: str = None) -> dict:
    """Load crawl config from JSON file"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def url_to_slug(base_url: str) -> str:
    """Convert URL to a safe directory slug"""
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    slug = parsed.netloc + parsed.path
    slug = slug.strip("/").replace("/", "_")
    import re
    return re.sub(r'[^\w\-_]', "_", slug)


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
            return canonical["href"].strip()
        og_url = soup.find("meta", attrs={"property": "og:url"})
        if og_url and og_url.get("content"):
            return og_url["content"].strip()
    except Exception:
        pass

    return fallback_url


def load_existing_html(raw_html_dir: Path, base_url: str = "") -> list[dict]:
    """Load pages from existing HTML files on disk"""
    if not raw_html_dir.exists():
        return []

    pages = []
    for html_file in raw_html_dir.glob("*.html"):
        content = html_file.read_text(encoding="utf-8")
        # Extract title from filename (URL slug -> readable)
        title = html_file.stem.replace("_", "/").replace("+", " ")
        if title == "index":
            fallback_url = base_url or title
        elif base_url:
            fallback_url = f"{base_url.rstrip('/')}/{title.lstrip('/')}"
        else:
            fallback_url = title
        source_url = _extract_source_url_from_html(content, fallback_url=fallback_url)
        pages.append({
            "url": source_url,
            "title": title,
            "html": content,
            "filename": html_file.name,
        })
    return pages


def vectorstore_has_data(persist_dir: str) -> bool:
    """Check if vectorstore already has documents (no model loading needed)"""
    persist_path = Path(persist_dir)
    if not persist_path.exists():
        return False
    # Chroma stores a file called "chroma.sqlite3" or has a "index.bin"
    has_data = (persist_path / "chroma.sqlite3").exists() or any(persist_path.glob("**/*.bin"))
    return has_data


async def crawl_and_index(
    base_url: str,
    output_dir: str = "./data",
    model_name: str = "BAAI/bge-m3",
    max_pages: int = 50,
    skip_crawl: bool = False,
    rebuild: bool = False,
):
    """Crawl docs and build index"""
    from crawlers.gitbook_crawler import GitBookCrawler
    from parsers.html_to_markdown import HTMLToMarkdownConverter
    from parsers.markdown_parser import MarkdownParser
    from chunkers.semantic_chunker import blocks_to_documents
    from embedders.embedding_pipeline import create_embedding_pipeline

    raw_html_dir = Path(output_dir) / "raw_html"
    vectorstore_dir = Path(output_dir) / "vectorstore"

    # ── Step 1: Crawl (or load from disk) ──────────────────────────────────────
    pages = []

    if rebuild and not skip_crawl:
        # Full recrawl + rebuild
        print("\n[Step 1/4] Rebuild mode: crawling fresh...")
        if raw_html_dir.exists():
            import shutil
            shutil.rmtree(raw_html_dir)
        crawler = GitBookCrawler(
            base_url=base_url,
            output_dir=str(raw_html_dir)
        )
        pages = await crawler.crawl(max_pages=max_pages)
    elif skip_crawl:
        # Reuse existing HTML (works for both rebuild/non-rebuild)
        pages = load_existing_html(raw_html_dir, base_url=base_url)
        if not pages:
            print("Error: --skip-crawl specified but no HTML files found. Run without --skip-crawl first.")
            sys.exit(1)
        mode = "rebuild mode: loaded" if rebuild else "loaded"
        print(f"\n[Step 1/4] {mode} {len(pages)} HTML files from disk")
    else:
        # Default behavior: reuse existing HTML when available, otherwise crawl
        existing = load_existing_html(raw_html_dir, base_url=base_url)
        if existing:
            print(f"\n[Step 1/4] Loading {len(existing)} existing HTML files from disk (skip crawl)")
            pages = existing
        else:
            print(f"\n[Step 1/4] Crawling from {base_url}...")
            crawler = GitBookCrawler(
                base_url=base_url,
                output_dir=str(raw_html_dir)
            )
            pages = await crawler.crawl(max_pages=max_pages)

    print(f"Crawl/Load complete: {len(pages)} pages")

    # ── Step 2: Parse ─────────────────────────────────────────────────────────
    print("\n[Step 2/4] Parsing...")
    converter = HTMLToMarkdownConverter()
    parser = MarkdownParser()

    all_blocks = []
    for page in pages:
        markdown_text = converter.convert(page["html"], base_url=page["url"])
        blocks = parser.parse(markdown_text)

        for block in blocks:
            block.source_url = page["url"]

        all_blocks.extend(blocks)
        print(f"  {page['title'][:50]}: {len(blocks)} blocks")

    print(f"Parse complete: {len(all_blocks)} blocks total")

    # ── Step 3: Chunk ──────────────────────────────────────────────────────────
    print("\n[Step 3/4] Chunking...")
    documents = blocks_to_documents(all_blocks)
    print(f"Chunking complete: {len(documents)} chunks")

    # ── Step 4: Embed + Store ────────────────────────────────────────────────
    if not rebuild and vectorstore_has_data(str(vectorstore_dir)):
        print(f"\n[Step 4/4] Vectorstore already has data, skipping embed (use --rebuild to overwrite)")
    else:
        print("\n[Step 4/4] Embedding + Storing...")
        if rebuild:
            print("  (rebuild mode, clearing existing vectorstore)")
            import shutil
            if vectorstore_dir.exists():
                shutil.rmtree(vectorstore_dir)

        pipeline = create_embedding_pipeline(
            model_name=model_name,
            persist_dir=str(vectorstore_dir)
        )
        pipeline.add_documents(documents)
        print(f"Storage complete: {len(documents)} documents")

    print("\n[OK] Index ready!")
    print(f"   Data dir: {output_dir}")
    print(f"   Vectorstore: {vectorstore_dir}")


def main():
    parser = argparse.ArgumentParser(description="Build RAG index")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: .crawl_config.json)"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="GitBook URL to crawl (overrides config)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./data",
        help="Output directory"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Embedding model name (overrides config)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages to crawl (overrides config)"
    )
    parser.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip crawling, use existing HTML files from previous crawl"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force full rebuild (re-crawl and re-embed)"
    )

    args = parser.parse_args()

    # Load config file
    config = load_config(args.config)

    # CLI args override config file
    base_url = args.url or config.get("base_url")
    max_pages = args.max_pages or config.get("max_pages", 50)
    model_name = args.model or config.get("model", "BAAI/bge-m3")

    if not base_url:
        print("Error: No URL specified. Use --url or set base_url in .crawl_config.json")
        sys.exit(1)

    asyncio.run(crawl_and_index(
        base_url=base_url,
        output_dir=args.output,
        model_name=model_name,
        max_pages=max_pages,
        skip_crawl=args.skip_crawl,
        rebuild=args.rebuild,
    ))


if __name__ == "__main__":
    main()
