import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.parsers.markdown_parser import MarkdownParser


class MarkdownParserTests(unittest.TestCase):
    def test_ordered_list_with_nested_items_keeps_parent_text(self):
        markdown = "1. Install package\n   - pip install x\n2. Run app\n"
        blocks = MarkdownParser().parse(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "ordered_list")
        self.assertEqual(len(blocks[0].items), 2)
        self.assertIn("Install package", blocks[0].items[0])
        self.assertIn("- pip install x", blocks[0].items[0])
        self.assertEqual(blocks[0].items[1], "Run app")

    def test_plain_text_with_pipe_is_not_table(self):
        markdown = "A | B but this is plain text, not a table."
        blocks = MarkdownParser().parse(markdown)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "text")
        self.assertEqual(blocks[0].content, markdown)


if __name__ == "__main__":
    unittest.main()
