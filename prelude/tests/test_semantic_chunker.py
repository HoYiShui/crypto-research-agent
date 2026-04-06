import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.chunkers.semantic_chunker import SemanticChunker
from rag.parsers.markdown_parser import MarkdownBlock


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

    def test_orphan_heading_blocks_are_not_merged_into_single_chunk(self):
        chunker = SemanticChunker(max_tokens_per_chunk=4096)
        blocks = [
            MarkdownBlock(
                block_id="b1",
                heading_path=[],
                heading_level=1,
                block_type="text",
                content="nav part 1",
                source_url="https://example.com/doc",
            ),
            MarkdownBlock(
                block_id="b2",
                heading_path=[],
                heading_level=1,
                block_type="text",
                content="nav part 2",
                source_url="https://example.com/doc",
            ),
            MarkdownBlock(
                block_id="b3",
                heading_path=["Main Title"],
                heading_level=1,
                block_type="text",
                content="real content",
                source_url="https://example.com/doc",
            ),
        ]

        chunks = chunker.chunk(blocks)
        orphan_chunks = [c for c in chunks if not any(str(h).strip() for h in c.heading_path)]
        self.assertEqual(len(orphan_chunks), 2)


if __name__ == "__main__":
    unittest.main()
