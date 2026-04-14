import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.pipeline_config import DEFAULT_PIPELINE_CONFIG, load_pipeline_config


class PipelineConfigTests(unittest.TestCase):
    def test_load_pipeline_config_uses_defaults_when_missing(self):
        cfg = load_pipeline_config("/tmp/not-found-rag-pipeline.yaml")
        self.assertEqual(cfg["embedding"]["model"], DEFAULT_PIPELINE_CONFIG["embedding"]["model"])
        self.assertEqual(
            cfg["chunking"]["max_tokens_per_chunk"],
            DEFAULT_PIPELINE_CONFIG["chunking"]["max_tokens_per_chunk"],
        )

    def test_load_pipeline_config_merges_partial_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "rag_pipeline.yaml"
            cfg_path.write_text(
                yaml.safe_dump(
                    {
                        "chunking": {"max_tokens_per_chunk": 888},
                        "embedding": {"batch_size": 2},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            cfg = load_pipeline_config(str(cfg_path))

        self.assertEqual(cfg["chunking"]["max_tokens_per_chunk"], 888)
        self.assertEqual(cfg["embedding"]["batch_size"], 2)
        self.assertEqual(
            cfg["embedding"]["model"],
            DEFAULT_PIPELINE_CONFIG["embedding"]["model"],
        )


if __name__ == "__main__":
    unittest.main()
