"""
pi_bridge.py: Python Agent bridge for Pi-mono TUI

The TUI spawns this script as a subprocess and communicates via JSONL over stdio.

Protocol (one JSON object per line):
  TUI -> Bridge: {"type": "user_message", "content": "..."}
  TUI -> Bridge: {"type": "reset"}

  Bridge -> TUI: {"type": "assistant_message", "content": "..."}
  Bridge -> TUI: {"type": "tool_call", "name": "...", "args": {...}}
  Bridge -> TUI: {"type": "tool_result", "name": "...", "content": "..."}
  Bridge -> TUI: {"type": "reset_done"}
  Bridge -> TUI: {"type": "error", "content": "..."}

Startup signal (on stderr, consumed by TUI):
  BRIDGE_READY
"""
import json
import sys
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agent.agent_loop import MinimalAgent


def send(msg: dict):
    """Write a JSONL message to stdout."""
    print(json.dumps(msg), flush=True)


class PiBridge:
    DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"

    def __init__(self):
        self.agent: MinimalAgent | None = None
        self.project_root = Path(__file__).resolve().parents[2]
        self._vectorstore = None
        self._vectorstore_last_error: str | None = None
        self._vectorstore_last_attempt_ts: float | None = None
        self._vectorstore_retry_interval_sec = int(os.getenv("VECTORSTORE_RETRY_INTERVAL_SEC", "30"))

    def _resolve_embedding_model(self) -> str:
        return os.getenv("EMBEDDING_MODEL") or self.DEFAULT_EMBEDDING_MODEL

    def _load_vectorstore_lazy(self):
        if self._vectorstore is not None:
            return self._vectorstore

        now = time.monotonic()
        if self._vectorstore_last_attempt_ts is not None:
            elapsed = now - self._vectorstore_last_attempt_ts
            if elapsed < self._vectorstore_retry_interval_sec:
                wait_sec = int(self._vectorstore_retry_interval_sec - elapsed)
                reason = self._vectorstore_last_error or "previous initialization failed"
                raise RuntimeError(f"{reason} (retry in ~{wait_sec}s)")

        self._vectorstore_last_attempt_ts = now
        vectorstore_dir = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
        embedding_model = self._resolve_embedding_model()

        try:
            from rag.embedders.embedding_pipeline import create_embedding_pipeline

            self._vectorstore = create_embedding_pipeline(
                model_name=embedding_model,
                persist_dir=vectorstore_dir,
            )
            print(
                f"Vectorstore loaded lazily (model={embedding_model}, dir={vectorstore_dir})",
                file=sys.stderr,
                flush=True,
            )
            self._vectorstore_last_error = None
        except Exception as e:
            self._vectorstore_last_error = str(e)
            print(
                f"Vectorstore unavailable (model={embedding_model}, dir={vectorstore_dir}): {e}",
                file=sys.stderr,
                flush=True,
            )
            self._vectorstore = None
            raise RuntimeError(self._vectorstore_last_error) from e

        return self._vectorstore

    def initialize(self):
        self.agent = MinimalAgent(
            vectorstore=None,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result,
        )
        self.agent.set_vectorstore_loader(self._load_vectorstore_lazy)

        # Signal ready to TUI
        print("BRIDGE_READY", file=sys.stderr, flush=True)

    def _on_tool_call(self, name: str, args: dict):
        send({"type": "tool_call", "name": name, "args": args})

    def _on_tool_result(self, name: str, content: str):
        send({"type": "tool_result", "name": name, "content": content[:300]})

    def handle(self, msg: dict):
        msg_type = msg.get("type", "")

        if msg_type == "user_message":
            content = msg.get("content", "")
            try:
                response = self.agent.chat(content)
                send({"type": "assistant_message", "content": response})
            except Exception as e:
                send({"type": "error", "content": str(e)})

        elif msg_type == "reset":
            self.agent.reset()
            send({"type": "reset_done"})

        elif msg_type == "ping":
            send({"type": "pong"})

    def run(self):
        self.initialize()
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                self.handle(msg)
            except json.JSONDecodeError:
                continue


if __name__ == "__main__":
    PiBridge().run()
