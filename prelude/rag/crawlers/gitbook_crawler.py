"""
GitBook Crawler: Crawls GitBook documentation sites
"""
import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
except ImportError as e:
    raise SystemExit(
        "Please install dependencies: playwright, beautifulsoup4, and run 'playwright install chromium'"
    ) from e


class GitBookCrawler:
    """Crawls GitBook documentation sites"""

    def __init__(self, base_url: str, output_dir: str = "./data/raw_html"):
        self.base_url = base_url.rstrip("/")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.visited_urls = set()

    async def _goto_page(self, page, url: str) -> None:
        """
        Navigate to url with a resilient strategy:
        - try networkidle first for fully-loaded pages
        - fallback to domcontentloaded for sites with long-polling/streaming traffic
        """
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            return
        except PlaywrightTimeoutError:
            print(f"[WARN] networkidle timeout for {url}, fallback to domcontentloaded")

        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        # Give dynamic docs pages a short settle window after DOM is ready.
        await page.wait_for_timeout(1200)

    async def crawl(self, max_pages: int = 100) -> list[dict]:
        """
        Crawl all pages, return list of {url, title, html}
        """
        pages = []
        queue = [self.base_url]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            while queue and len(pages) < max_pages:
                url = queue.pop(0)
                if url in self.visited_urls:
                    continue

                self.visited_urls.add(url)
                print(f"Crawling: {url}")

                try:
                    await self._goto_page(page, url)
                    content = await page.content()
                    title = await page.title()

                    # Save HTML
                    filename = self._url_to_filename(url)
                    filepath = self.output_dir / f"{filename}.html"
                    filepath.write_text(content)

                    pages.append({
                        "url": url,
                        "title": title,
                        "html": content,
                        "filename": f"{filename}.html",
                    })

                    # Extract sub-page links
                    links = await self._extract_links(page, url)
                    for link in links:
                        if link not in self.visited_urls and link.startswith(self.base_url):
                            queue.append(link)

                except Exception as e:
                    print(f"Error crawling {url}: {e}")

            await browser.close()

        print(f"Crawled {len(pages)} pages")
        return pages

    async def _extract_links(self, page, current_url: str) -> list[str]:
        """Extract all sub-page links from the page"""
        links = await page.query_selector_all("a[href]")
        result = []
        for link in links:
            href = await link.get_attribute("href")
            if href:
                full_url = urljoin(current_url, href)
                # Only keep links from the same site
                if full_url.startswith(self.base_url) and "#" not in full_url:
                    result.append(full_url)
        return list(set(result))

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to filename"""
        path = url.replace(self.base_url, "")
        path = path.strip("/").replace("/", "_")
        if not path:
            return "index"
        # Clean illegal characters
        return re.sub(r'[^\w\-_]', "_", path)


async def crawl_hyperliquid_docs():
    """Crawl Hyperliquid documentation"""
    crawler = GitBookCrawler(
        base_url="https://hyperliquid.gitbook.io/hyperliquid-docs/",
        output_dir="./data/raw_html/hyperliquid"
    )
    pages = await crawler.crawl(max_pages=50)
    return pages


if __name__ == "__main__":
    pages = asyncio.run(crawl_hyperliquid_docs())
    print(f"\nTotal pages: {len(pages)}")
