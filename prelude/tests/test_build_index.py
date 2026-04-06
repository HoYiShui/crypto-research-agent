import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_index import (
    _extract_source_url_from_html,
    CrawlSite,
    cleanup_for_rebuild,
    has_local_site_cache,
    resolve_sources,
    resolve_start_stage,
)


class BuildIndexTests(unittest.TestCase):
    def test_resolve_start_stage_defaults_to_crawl(self):
        self.assertEqual(resolve_start_stage(None), "crawl")

    def test_resolve_start_stage_respects_explicit_stage(self):
        self.assertEqual(resolve_start_stage("chunk"), "chunk")

    def test_extract_source_url_prefers_canonical(self):
        html = """
        <html>
          <head>
            <meta property="og:url" content="https://docs.example.com/from-og"/>
            <link rel="canonical" href="https://docs.example.com/from-canonical"/>
          </head>
          <body>hello</body>
        </html>
        """
        url = _extract_source_url_from_html(html, fallback_url="https://fallback.example.com")
        self.assertEqual(url, "https://docs.example.com/from-canonical")

    def test_extract_source_url_falls_back_when_missing(self):
        html = "<html><head></head><body>hello</body></html>"
        fallback = "https://fallback.example.com/page"
        url = _extract_source_url_from_html(html, fallback_url=fallback)
        self.assertEqual(url, fallback)

    def test_resolve_sources_uses_enabled_sites(self):
        config = {
            "max_page": 20,
            "site": [
                {
                    "name": "hyperliquid",
                    "type": "gitbook",
                    "base_url": "https://hyperliquid.gitbook.io/hyperliquid-docs/",
                    "enable": True,
                }
            ],
        }
        sites, max_page = resolve_sources(config=config, url_override=None, max_pages_override=None)
        self.assertEqual(max_page, 20)
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].name, "hyperliquid")

    def test_resolve_sources_filters_disabled_sites(self):
        config = {
            "max_page": 10,
            "site": [
                {
                    "name": "a",
                    "type": "gitbook",
                    "base_url": "https://a.example.com",
                    "enable": False,
                },
                {
                    "name": "b",
                    "type": "gitbook",
                    "base_url": "https://b.example.com",
                    "enable": True,
                },
            ],
        }
        sites, _ = resolve_sources(config=config, url_override=None, max_pages_override=None)
        self.assertEqual([s.name for s in sites], ["b"])

    def test_resolve_sources_errors_when_no_enabled_sites(self):
        config = {
            "max_page": 10,
            "site": [
                {
                    "name": "a",
                    "type": "gitbook",
                    "base_url": "https://a.example.com",
                    "enable": False,
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "No enabled source"):
            resolve_sources(config=config, url_override=None, max_pages_override=None)

    def test_resolve_sources_accepts_url_override(self):
        config = {"max_page": 10}
        sites, max_page = resolve_sources(
            config=config,
            url_override="https://docs.example.com/",
            max_pages_override=None,
        )
        self.assertEqual(len(sites), 1)
        self.assertEqual(sites[0].type, "gitbook")
        self.assertEqual(sites[0].base_url, "https://docs.example.com/")
        self.assertEqual(max_page, 10)

    def test_has_local_site_cache_detects_html_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            site_dir = Path(tmp) / "raw_html" / "demo"
            site_dir.mkdir(parents=True, exist_ok=True)
            self.assertFalse(has_local_site_cache(site_dir))

            (site_dir / "index.html").write_text("<html></html>", encoding="utf-8")
            self.assertTrue(has_local_site_cache(site_dir))

    def test_cleanup_for_rebuild_removes_only_selected_site_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_html_root = root / "raw_html"
            site_a_dir = raw_html_root / "site-a"
            site_b_dir = raw_html_root / "site-b"
            site_a_dir.mkdir(parents=True, exist_ok=True)
            site_b_dir.mkdir(parents=True, exist_ok=True)
            (site_a_dir / "index.html").write_text("<html>a</html>", encoding="utf-8")
            (site_b_dir / "index.html").write_text("<html>b</html>", encoding="utf-8")

            cleanup_for_rebuild(
                start_stage="crawl",
                raw_html_root=raw_html_root,
                sites=[CrawlSite(name="site-a", type="gitbook", base_url="https://a.example.com")],
                parsed_blocks_path=root / "parsed_blocks.jsonl",
                chunks_path=root / "chunks.jsonl",
                vectorstore_dir=root / "vectorstore",
            )

            self.assertFalse(site_a_dir.exists())
            self.assertTrue(site_b_dir.exists())


if __name__ == "__main__":
    unittest.main()
