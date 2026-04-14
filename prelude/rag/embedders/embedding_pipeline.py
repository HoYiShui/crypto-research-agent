"""
Embedding Pipeline: Document[] -> Chroma Vector DB

Uses sentence-transformers and chromadb directly, no LangChain.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import uuid
import os

from rag.pipeline_config import get_embedding_config

# Load HF_TOKEN from environment (for authenticated downloads)
HF_TOKEN = os.getenv("HF_TOKEN")
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN

try:
    import sentence_transformers
    import chromadb
    from chromadb.config import Settings
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install: uv add sentence-transformers chromadb")
    raise SystemExit(1)


@dataclass
class Document:
    """Simple document container (no LangChain dependency)"""
    page_content: str
    metadata: dict = field(default_factory=dict)


class EmbeddingPipeline:
    """
    Embedding pipeline using sentence-transformers + Chroma

    Args:
        model_name: HuggingFace model name (default: BAAI/bge-m3)
        encode_kwargs: Additional args for encode()
        vectorstore_dir: Directory to persist Chroma db
    """

    def __init__(
        self,
        model_name: str | None = None,
        encode_kwargs: dict | None = None,
        vectorstore_dir: str = "./data/vectorstore",
        batch_size: int | None = None,
        max_seq_length: int | None = None,
    ):
        cfg = get_embedding_config()

        self.model_name = model_name or str(cfg.get("model", "BAAI/bge-m3"))
        normalize_embeddings = bool(cfg.get("normalize_embeddings", True))
        self.encode_kwargs = {"normalize_embeddings": normalize_embeddings}
        if encode_kwargs:
            self.encode_kwargs.update(encode_kwargs)

        self.batch_size = int(batch_size if batch_size is not None else cfg.get("batch_size", 4))
        self.max_seq_length = int(
            max_seq_length if max_seq_length is not None else cfg.get("max_seq_length", 1024)
        )
        self.vectorstore_dir = Path(vectorstore_dir)
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)

        # Load embedding model (prefer local HF snapshot to avoid network flakiness)
        self.model = self._load_embedding_model(self.model_name)
        if hasattr(self.model, "max_seq_length") and self.max_seq_length > 0:
            self.model.max_seq_length = self.max_seq_length

        # Chroma client (persistent)
        self._client = chromadb.PersistentClient(
            path=str(self.vectorstore_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        self._collection = None

    def _resolve_local_snapshot_path(self, model_name: str) -> Optional[Path]:
        """Return local HF snapshot path if available, else None."""
        if "/" not in model_name:
            return None

        cache_root = Path.home() / ".cache" / "huggingface" / "hub"
        repo_dir = cache_root / f"models--{model_name.replace('/', '--')}"
        snapshots_dir = repo_dir / "snapshots"
        refs_main = repo_dir / "refs" / "main"

        if not snapshots_dir.exists():
            return None

        # Prefer refs/main when present
        if refs_main.exists():
            try:
                revision = refs_main.read_text(encoding="utf-8").strip()
                snapshot = snapshots_dir / revision
                if snapshot.exists():
                    return snapshot
            except Exception:
                pass

        # Fallback to latest snapshot by mtime
        candidates = [p for p in snapshots_dir.iterdir() if p.is_dir()]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.stat().st_mtime)

    def _load_embedding_model(self, model_name: str):
        """Load sentence-transformers model with local-first strategy."""
        local_snapshot = self._resolve_local_snapshot_path(model_name)
        errors = []

        if local_snapshot is not None:
            try:
                return sentence_transformers.SentenceTransformer(
                    str(local_snapshot),
                    local_files_only=True,
                )
            except Exception as e:
                errors.append(f"local snapshot load failed ({local_snapshot}): {e}")

        try:
            return sentence_transformers.SentenceTransformer(model_name)
        except Exception as e:
            errors.append(f"remote/model-id load failed ({model_name}): {e}")
            raise RuntimeError(" | ".join(errors))

    def _get_collection(self):
        """Get or create Chroma collection"""
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"}
            )
        return self._collection

    def add_documents(self, documents: list, ids: list = None):
        """Add documents to vectorstore"""
        if not documents:
            return

        collection = self._get_collection()

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]

        # Encode texts
        texts = [doc.page_content for doc in documents]
        embeddings = self.model.encode(texts, batch_size=self.batch_size, **self.encode_kwargs)

        # Add to Chroma
        metadatas = [doc.metadata for doc in documents]
        collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas
        )

    def search(
        self,
        query: str,
        k: int = 5,
        filter_dict: dict = None
    ) -> list:
        """
        Search for most relevant documents

        Returns:
            list of (Document, score) tuples
        """
        collection = self._get_collection()

        query_embedding = self.model.encode([query], **self.encode_kwargs)

        results = collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=k,
            where=filter_dict,
        )

        # Convert to (Document, score) tuples
        output = []
        if results["documents"] and results["documents"][0]:
            for i, doc_text in enumerate(results["documents"][0]):
                doc = Document(
                    page_content=doc_text,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {}
                )
                score = results["distances"][0][i] if results["distances"] else 0.0
                output.append((doc, score))

        return output

    def as_retriever(self, **kwargs):
        """Return a simple retriever interface (for compatibility)"""
        return self


def create_embedding_pipeline(
    model_name: str | None = None,
    persist_dir: str = "./data/vectorstore",
    batch_size: int | None = None,
    max_seq_length: int | None = None,
) -> EmbeddingPipeline:
    """Factory function to create EmbeddingPipeline"""
    return EmbeddingPipeline(
        model_name=model_name,
        vectorstore_dir=persist_dir,
        batch_size=batch_size,
        max_seq_length=max_seq_length,
    )
