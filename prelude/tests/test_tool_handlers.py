import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools import ToolHandlers


class _Doc:
    def __init__(self, content: str, metadata: dict):
        self.page_content = content
        self.metadata = metadata


class _Vectorstore:
    def search(self, query: str, k: int = 5):
        return [
            (
                _Doc(
                    content=f"match for {query}",
                    metadata={"source_url": "https://example.com", "heading_path": "A > B"},
                ),
                0.12,
            )
        ]


class ToolHandlersTests(unittest.TestCase):
    def test_rag_search_uses_lazy_loader_once(self):
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return _Vectorstore()

        handlers = ToolHandlers(vectorstore=None, vectorstore_loader=loader)

        out1 = handlers.execute("rag_search", {"query": "fees"})
        out2 = handlers.execute("rag_search", {"query": "tokenomics"})

        self.assertIn("Source: https://example.com", out1)
        self.assertIn("match for tokenomics", out2)
        self.assertEqual(calls["count"], 1)

    def test_rag_search_loader_failure_returns_error(self):
        def loader():
            raise RuntimeError("cannot init")

        handlers = ToolHandlers(vectorstore=None, vectorstore_loader=loader)
        out = handlers.execute("rag_search", {"query": "fees"})
        self.assertIn("RAG_UNAVAILABLE:", out)
        self.assertIn("Failed to initialize vectorstore lazily", out)


if __name__ == "__main__":
    unittest.main()
