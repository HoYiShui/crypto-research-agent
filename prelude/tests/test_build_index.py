import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_index import _extract_source_url_from_html


class BuildIndexTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
