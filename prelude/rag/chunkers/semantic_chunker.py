"""
Semantic Chunker: Convert MarkdownBlock[] to Document[]
"""
from dataclasses import dataclass, field
from pathlib import Path

from rag.parsers.markdown_parser import MarkdownBlock, block_to_embedding_text
from rag.pipeline_config import get_chunking_config, get_embedding_config


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

    MAX_TOKENS_PER_CHUNK = 1024
    WARN_TOKENS_PER_CHUNK = 768

    def __init__(
        self,
        max_tokens_per_chunk: int | None = None,
        warn_tokens_per_chunk: int | None = None,
    ):
        cfg = get_chunking_config()
        emb_cfg = get_embedding_config()
        self.MAX_TOKENS_PER_CHUNK = int(
            max_tokens_per_chunk
            if max_tokens_per_chunk is not None
            else cfg.get("max_tokens_per_chunk", self.MAX_TOKENS_PER_CHUNK)
        )
        self.WARN_TOKENS_PER_CHUNK = int(
            warn_tokens_per_chunk
            if warn_tokens_per_chunk is not None
            else cfg.get("warn_tokens_per_chunk", self.WARN_TOKENS_PER_CHUNK)
        )
        self.embedding_model_name = str(emb_cfg.get("model", "BAAI/bge-m3"))
        self.chunk_counter = 0
        self._tokenizer = None
        self._tokenizer_init_attempted = False

    def _resolve_local_snapshot_path(self, model_name: str) -> Path | None:
        if "/" not in model_name:
            p = Path(model_name)
            return p if p.exists() else None

        cache_root = Path.home() / ".cache" / "huggingface" / "hub"
        repo_dir = cache_root / f"models--{model_name.replace('/', '--')}"
        snapshots_dir = repo_dir / "snapshots"
        refs_main = repo_dir / "refs" / "main"

        if not snapshots_dir.exists():
            return None

        if refs_main.exists():
            try:
                revision = refs_main.read_text(encoding="utf-8").strip()
                snapshot = snapshots_dir / revision
                if snapshot.exists():
                    return snapshot
            except Exception:
                pass

        candidates = [p for p in snapshots_dir.iterdir() if p.is_dir()]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _get_model_tokenizer(self):
        if self._tokenizer_init_attempted:
            return self._tokenizer

        self._tokenizer_init_attempted = True
        try:
            from transformers import AutoTokenizer

            local_snapshot = self._resolve_local_snapshot_path(self.embedding_model_name)
            if local_snapshot is not None:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    str(local_snapshot),
                    local_files_only=True,
                )
                # Token counting only: disable model sequence-length warning noise.
                self._tokenizer.model_max_length = 10**9
                return self._tokenizer
        except Exception:
            self._tokenizer = None

        return self._tokenizer

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
        # Guard rail: do not aggressively merge all orphan blocks (empty heading path),
        # otherwise large navigation/noise sections may become one oversized chunk.
        is_orphan_heading = (not heading_path) or all((not str(h).strip()) for h in heading_path)
        if is_orphan_heading and len(blocks) > 1:
            orphan_chunks: list[Chunk] = []
            for block in blocks:
                orphan_chunks.extend(self._process_group(heading_path, [block]))
            return orphan_chunks

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

            if piece_tokens > self.MAX_TOKENS_PER_CHUNK:
                if bucket:
                    chunks.append(self._make_chunk(heading_path, bucket, "text"))
                    bucket = []
                    bucket_tokens = 0
                chunks.extend(self._split_single_oversized_piece(heading_path, block, piece))
                continue

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

    def _split_single_oversized_piece(
        self,
        heading_path: tuple,
        block: MarkdownBlock,
        piece: str,
    ) -> list[Chunk]:
        """
        Split one oversized text piece by whitespace token budget.
        This is a final fallback to guarantee chunk size constraints.
        """
        words = piece.split()
        if not words:
            return [self._make_chunk(heading_path, [block], "text")]

        chunks: list[Chunk] = []
        bucket_words: list[str] = []

        def flush_bucket() -> None:
            nonlocal bucket_words
            if not bucket_words:
                return
            text = " ".join(bucket_words)
            piece_block = MarkdownBlock(
                block_id=block.block_id,
                heading_path=block.heading_path,
                heading_level=block.heading_level,
                block_type=block.block_type,
                content=text,
                source_url=block.source_url,
                raw_markdown=text,
            )
            chunks.append(self._make_chunk(heading_path, [piece_block], "text"))
            bucket_words = []

        for word in words:
            candidate_words = bucket_words + [word]
            candidate_text = " ".join(candidate_words)
            candidate_block = MarkdownBlock(
                block_id=block.block_id,
                heading_path=block.heading_path,
                heading_level=block.heading_level,
                block_type=block.block_type,
                content=candidate_text,
                source_url=block.source_url,
                raw_markdown=candidate_text,
            )
            candidate_tokens = self._estimate_tokens(block_to_embedding_text(candidate_block))

            if not bucket_words and candidate_tokens > self.MAX_TOKENS_PER_CHUNK:
                # Extremely long standalone token/word fallback.
                text = word
                while text:
                    window = text[:256]
                    text = text[256:]
                    piece_block = MarkdownBlock(
                        block_id=block.block_id,
                        heading_path=block.heading_path,
                        heading_level=block.heading_level,
                        block_type=block.block_type,
                        content=window,
                        source_url=block.source_url,
                        raw_markdown=window,
                    )
                    chunks.append(self._make_chunk(heading_path, [piece_block], "text"))
                continue

            if bucket_words and candidate_tokens > self.MAX_TOKENS_PER_CHUNK:
                flush_bucket()
                bucket_words = [word]
            else:
                bucket_words = candidate_words

        flush_bucket()
        return chunks

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count with embedding-model tokenizer when available."""
        tokenizer = self._get_model_tokenizer()
        if tokenizer is not None:
            try:
                return len(tokenizer.encode(text, add_special_tokens=True, truncation=False))
            except Exception:
                pass

        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            # Fallback: chars/4
            return len(text) // 4


def blocks_to_documents(
    blocks: list[MarkdownBlock],
    max_tokens_per_chunk: int | None = None,
    warn_tokens_per_chunk: int | None = None,
) -> list[Document]:
    """Convert MarkdownBlocks to LangChain Documents"""
    chunker = SemanticChunker(
        max_tokens_per_chunk=max_tokens_per_chunk,
        warn_tokens_per_chunk=warn_tokens_per_chunk,
    )
    chunks = chunker.chunk(blocks)
    return [chunk.to_document() for chunk in chunks]
