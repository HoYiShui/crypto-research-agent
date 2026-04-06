import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.embedders.embedding_pipeline import EmbeddingPipeline


class EmbeddingPipelineTests(unittest.TestCase):
    def test_load_embedding_model_prefers_local_snapshot(self):
        pipeline = object.__new__(EmbeddingPipeline)
        fake_model = object()

        with patch.object(
            EmbeddingPipeline,
            "_resolve_local_snapshot_path",
            return_value=Path("/tmp/local-snapshot"),
        ), patch(
            "rag.embedders.embedding_pipeline.sentence_transformers.SentenceTransformer",
            return_value=fake_model,
        ) as mocked_loader:
            model = pipeline._load_embedding_model("sentence-transformers/all-MiniLM-L6-v2")

        self.assertIs(model, fake_model)
        mocked_loader.assert_called_once_with("/tmp/local-snapshot", local_files_only=True)

    def test_load_embedding_model_falls_back_to_model_id(self):
        pipeline = object.__new__(EmbeddingPipeline)
        fake_model = object()

        with patch.object(
            EmbeddingPipeline,
            "_resolve_local_snapshot_path",
            return_value=None,
        ), patch(
            "rag.embedders.embedding_pipeline.sentence_transformers.SentenceTransformer",
            return_value=fake_model,
        ) as mocked_loader:
            model = pipeline._load_embedding_model("sentence-transformers/all-MiniLM-L6-v2")

        self.assertIs(model, fake_model)
        mocked_loader.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")

    def test_load_embedding_model_reports_both_errors(self):
        pipeline = object.__new__(EmbeddingPipeline)

        with patch.object(
            EmbeddingPipeline,
            "_resolve_local_snapshot_path",
            return_value=Path("/tmp/local-snapshot"),
        ), patch(
            "rag.embedders.embedding_pipeline.sentence_transformers.SentenceTransformer",
            side_effect=[RuntimeError("local failed"), RuntimeError("remote failed")],
        ):
            with self.assertRaises(RuntimeError) as ctx:
                pipeline._load_embedding_model("sentence-transformers/all-MiniLM-L6-v2")

        msg = str(ctx.exception)
        self.assertIn("local snapshot load failed", msg)
        self.assertIn("remote/model-id load failed", msg)


if __name__ == "__main__":
    unittest.main()
