import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chunkers.semantic_chunker import SemanticChunker
from parsers.markdown_parser import MarkdownBlock


class SemanticChunkerTests(unittest.TestCase):
    def test_oversized_text_group_is_split_by_token_budget(self):
        chunker = SemanticChunker()
        paragraph = " ".join(f"word{i}" for i in range(1200))
        content = "\n\n".join([paragraph] * 6)

        blocks = [
            MarkdownBlock(
                block_id="b1",
                heading_path=["H1"],
                heading_level=1,
                block_type="text",
                content=content,
                source_url="https://example.com",
            )
        ]

        chunks = chunker.chunk(blocks)
        self.assertGreater(len(chunks), 1)

        token_sizes = [chunker._estimate_tokens(c.content_for_embedding) for c in chunks]
        self.assertTrue(all(t <= chunker.MAX_TOKENS_PER_CHUNK for t in token_sizes))


if __name__ == "__main__":
    unittest.main()
