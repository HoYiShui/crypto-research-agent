"""
Semantic Chunker: Convert MarkdownBlock[] to Document[]
"""
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from rag.parsers.markdown_parser import MarkdownBlock, block_to_embedding_text


@dataclass
class Document:
    """Simple document container (no LangChain dependency)"""
    page_content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    """A chunk ready for embedding"""
    chunk_id: str
    source_url: str
    heading_path: list[str]
    chunk_type: str
    heading_level: int
    content_for_embedding: str
    raw_block: MarkdownBlock

    def to_document(self) -> Document:
        return Document(
            page_content=self.content_for_embedding,
            metadata={
                "chunk_id": self.chunk_id,
                "source_url": self.source_url,
                "heading_path": str(self.heading_path),
                "chunk_type": self.chunk_type,
                "heading_level": self.heading_level,
            }
        )


class SemanticChunker:
    """
    Split MarkdownBlocks by semantics + heading boundaries

    Strategy:
    - Group blocks by heading_path
    - Text blocks: split by heading boundaries
    - Table blocks: whole table as one chunk (no token check)
    - Code blocks: whole function as one chunk
    """

    MAX_TOKENS_PER_CHUNK = 4096
    WARN_TOKENS_PER_CHUNK = 2048

    def __init__(self):
        self.chunk_counter = 0

    def _new_chunk_id(self) -> str:
        self.chunk_counter += 1
        return f"chunk_{self.chunk_counter}"

    def chunk(self, blocks: list[MarkdownBlock]) -> list[Chunk]:
        """
        Convert MarkdownBlock[] to Chunk[]

        Flow:
        1. Group by heading_path
        2. Check token count
        3. If over limit, split by subheadings
        """
        # Group by heading_path
        groups = self._group_by_heading(blocks)

        chunks = []
        for heading_path, group_blocks in groups.items():
            group_chunks = self._process_group(heading_path, group_blocks)
            chunks.extend(group_chunks)

        return chunks

    def _group_by_heading(self, blocks: list[MarkdownBlock]) -> dict:
        """Group blocks by heading_path"""
        groups = {}
        for block in blocks:
            key = tuple(block.heading_path) if block.heading_path else ("",)
            if key not in groups:
                groups[key] = []
            groups[key].append(block)
        return groups

    def _process_group(self, heading_path: tuple, blocks: list[MarkdownBlock]) -> list[Chunk]:
        """Process a single heading_path group"""
        chunks = []

        # Separate by block_type
        table_blocks = [b for b in blocks if b.block_type == "table"]
        code_blocks = [b for b in blocks if b.block_type == "code"]
        text_blocks = [b for b in blocks if b.block_type in ("text", "ordered_list", "unordered_list")]

        # Table and Code: whole block as one chunk (no token check)
        for block in table_blocks + code_blocks:
            chunks.append(self._make_chunk(heading_path, [block], block.block_type))

        # Text type: merge then check token count
        if text_blocks:
            merged_chunk = self._make_chunk(heading_path, text_blocks, "text")
            token_count = self._estimate_tokens(merged_chunk.content_for_embedding)

            if token_count <= self.MAX_TOKENS_PER_CHUNK:
                chunks.append(merged_chunk)
            else:
                # Over limit, split by token budget
                sub_chunks = self._split_by_token_budget(heading_path, text_blocks)
                chunks.extend(sub_chunks)

        return chunks

    def _make_chunk(self, heading_path: tuple, blocks: list[MarkdownBlock], chunk_type: str) -> Chunk:
        """Create a Chunk"""
        heading_list = list(heading_path)

        # Merge block contents
        contents = []
        for block in blocks:
            text = block_to_embedding_text(block)
            if text:
                contents.append(text)

        content = "\n\n".join(contents)

        # Find max heading_level
        max_level = max((b.heading_level for b in blocks), default=1)

        # Find source_url
        source_url = next((b.source_url for b in blocks if b.source_url), "")

        return Chunk(
            chunk_id=self._new_chunk_id(),
            source_url=source_url,
            heading_path=heading_list,
            chunk_type=chunk_type,
            heading_level=max_level,
            content_for_embedding=content,
            raw_block=blocks[0] if blocks else None,
        )

    def _split_by_subheading(self, heading_path: tuple, blocks: list[MarkdownBlock]) -> list[Chunk]:
        """Split by subheadings"""
        chunks = []
        current_subgroup = []
        current_subheading = None

        for block in blocks:
            if block.heading_level > heading_path.__len__():
                # This is a subheading
                if current_subheading is None or block.heading_level <= len(heading_path) + 1:
                    # Save current subgroup
                    if current_subgroup:
                        chunks.append(self._make_chunk(
                            list(heading_path) + [current_subheading or ""],
                            current_subgroup,
                            "text"
                        ))
                    current_subgroup = [block]
                    current_subheading = block.content.split('\n')[0] if block.content else None
                else:
                    # Deeper nesting, add to current subgroup
                    current_subgroup.append(block)
            else:
                current_subgroup.append(block)

        # Save last subgroup
        if current_subgroup:
            chunks.append(self._make_chunk(
                list(heading_path) + [current_subheading or ""],
                current_subgroup,
                "text"
            ))

        return chunks

    def _split_by_token_budget(self, heading_path: tuple, blocks: list[MarkdownBlock]) -> list[Chunk]:
        """Split blocks into multiple chunks under MAX_TOKENS_PER_CHUNK."""
        chunks = []
        current_blocks = []
        current_tokens = 0

        for block in blocks:
            block_text = block_to_embedding_text(block)
            block_tokens = self._estimate_tokens(block_text)

            if block_tokens > self.MAX_TOKENS_PER_CHUNK:
                # Flush current bucket first.
                if current_blocks:
                    chunks.append(self._make_chunk(heading_path, current_blocks, "text"))
                    current_blocks = []
                    current_tokens = 0

                chunks.extend(self._split_single_large_block(heading_path, block))
                continue

            if current_blocks and current_tokens + block_tokens > self.MAX_TOKENS_PER_CHUNK:
                chunks.append(self._make_chunk(heading_path, current_blocks, "text"))
                current_blocks = [block]
                current_tokens = block_tokens
            else:
                current_blocks.append(block)
                current_tokens += block_tokens

        if current_blocks:
            chunks.append(self._make_chunk(heading_path, current_blocks, "text"))

        return chunks

    def _split_single_large_block(self, heading_path: tuple, block: MarkdownBlock) -> list[Chunk]:
        """Split an oversized text block into smaller blocks by paragraph/line."""
        if not block.content:
            return [self._make_chunk(heading_path, [block], "text")]

        pieces = [p for p in block.content.split("\n\n") if p.strip()]
        if len(pieces) <= 1:
            pieces = [p for p in block.content.split("\n") if p.strip()]
        if not pieces:
            pieces = [block.content]

        chunks = []
        bucket = []
        bucket_tokens = 0

        for piece in pieces:
            piece_block = MarkdownBlock(
                block_id=block.block_id,
                heading_path=block.heading_path,
                heading_level=block.heading_level,
                block_type=block.block_type,
                content=piece,
                source_url=block.source_url,
                raw_markdown=piece,
            )
            piece_tokens = self._estimate_tokens(block_to_embedding_text(piece_block))

            if bucket and bucket_tokens + piece_tokens > self.MAX_TOKENS_PER_CHUNK:
                chunks.append(self._make_chunk(heading_path, bucket, "text"))
                bucket = [piece_block]
                bucket_tokens = piece_tokens
            else:
                bucket.append(piece_block)
                bucket_tokens += piece_tokens

        if bucket:
            chunks.append(self._make_chunk(heading_path, bucket, "text"))

        return chunks

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (simple: chars/4)"""
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            # Fallback: chars/4
            return len(text) // 4


def blocks_to_documents(blocks: list[MarkdownBlock]) -> list[Document]:
    """Convert MarkdownBlocks to LangChain Documents"""
    chunker = SemanticChunker()
    chunks = chunker.chunk(blocks)
    return [chunk.to_document() for chunk in chunks]
