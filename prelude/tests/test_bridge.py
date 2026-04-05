import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bridge.pi_bridge as pi_bridge


class _FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.loader = None

    def set_vectorstore_loader(self, loader):
        self.loader = loader


class BridgeTests(unittest.TestCase):
    def test_resolve_embedding_model_priority(self):
        bridge = pi_bridge.PiBridge()
        bridge._crawl_config = {"model": "config-model"}

        with patch.dict(os.environ, {"EMBEDDING_MODEL": "env-model"}, clear=False):
            self.assertEqual(bridge._resolve_embedding_model(), "env-model")

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bridge._resolve_embedding_model(), "config-model")

        bridge._crawl_config = {}
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bridge._resolve_embedding_model(), "BAAI/bge-m3")

    def test_initialize_sets_lazy_loader_without_loading(self):
        bridge = pi_bridge.PiBridge()
        called = {"count": 0}

        def fake_loader():
            called["count"] += 1
            return "vs"

        with patch.object(pi_bridge, "MinimalAgent", _FakeAgent):
            bridge._load_vectorstore_lazy = fake_loader
            bridge.initialize()

        self.assertIsInstance(bridge.agent, _FakeAgent)
        self.assertEqual(called["count"], 0)
        self.assertIsNotNone(bridge.agent.loader)
        self.assertEqual(bridge.agent.loader(), "vs")
        self.assertEqual(called["count"], 1)

    def test_lazy_vectorstore_respects_retry_interval(self):
        bridge = pi_bridge.PiBridge()
        bridge._vectorstore = None
        bridge._vectorstore_last_error = "network timeout"
        bridge._vectorstore_last_attempt_ts = 100.0
        bridge._vectorstore_retry_interval_sec = 30

        with patch("bridge.pi_bridge.time.monotonic", return_value=110.0):
            with self.assertRaises(RuntimeError) as ctx:
                bridge._load_vectorstore_lazy()

        self.assertIn("network timeout", str(ctx.exception))
        self.assertIn("retry in", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
