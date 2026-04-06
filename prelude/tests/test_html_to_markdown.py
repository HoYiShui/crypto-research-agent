import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.parsers.html_to_markdown import HTMLToMarkdownConverter


class HTMLToMarkdownConverterTests(unittest.TestCase):
    def test_extracts_main_content_and_removes_ui_noise(self):
        html = """
        <html>
          <body>
            <nav>search</nav>
            <main>
              <header>
                <h1>API</h1>
                <button>copy</button>
              </header>
              <div class="flex flex-col whitespace-pre-wrap">
                <p>Core documentation content.</p>
              </div>
              <div>Last updated 2 days ago</div>
            </main>
          </body>
        </html>
        """

        converter = HTMLToMarkdownConverter(use_markdownify=True)
        md = converter.convert(html)

        self.assertIn("# API", md)
        self.assertIn("Core documentation content.", md)
        self.assertNotIn("search", md.lower())
        self.assertNotIn("last updated", md.lower())
        self.assertNotIn("copy", md.lower())

    def test_normalizes_role_table_to_markdown_table(self):
        html = """
        <html>
          <body>
            <main>
              <header><h1>Specs</h1></header>
              <div class="flex flex-col whitespace-pre-wrap">
                <div role="table">
                  <div role="row">
                    <div role="columnheader">Symbol</div>
                    <div role="columnheader">Leverage</div>
                  </div>
                  <div role="row">
                    <div role="cell">BTC</div>
                    <div role="cell">50x</div>
                  </div>
                </div>
              </div>
            </main>
          </body>
        </html>
        """

        converter = HTMLToMarkdownConverter(use_markdownify=True)
        md = converter.convert(html)

        self.assertIn("| Symbol | Leverage |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("| BTC | 50x |", md)


if __name__ == "__main__":
    unittest.main()
