import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.agent_loop import MinimalAgent


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeMessagesAPI:
    def __init__(self):
        self.calls = 0
        self.captured_messages = []

    def create(self, **kwargs):
        self.calls += 1
        self.captured_messages.append(kwargs["messages"])

        if self.calls == 1:
            return _Obj(
                stop_reason="tool_use",
                content=[
                    _Obj(type="text", text="Need to inspect file first."),
                    _Obj(
                        type="tool_use",
                        id="toolu_1",
                        name="read_file",
                        input={"path": "README.md", "lines": 1},
                    ),
                ],
            )

        return _Obj(
            stop_reason="end_turn",
            content=[_Obj(type="text", text="done"), _Obj(type="text", text="final")],
        )


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessagesAPI()


class AgentLoopTests(unittest.TestCase):
    def test_tool_use_round_preserves_assistant_message(self):
        agent = MinimalAgent(api_key="x", base_url="https://example.com", model="x")
        agent.client = _FakeClient()

        out = agent.chat("hello", max_turns=3)

        self.assertEqual(out, "done\nfinal")
        self.assertEqual(len(agent.client.messages.captured_messages), 2)

        second_round_messages = agent.client.messages.captured_messages[1]
        assistant_blocks = [
            m for m in second_round_messages
            if m.get("role") == "assistant" and isinstance(m.get("content"), list)
        ]
        self.assertTrue(
            assistant_blocks,
            "assistant tool_use message should be preserved before tool_result",
        )
        self.assertTrue(
            any(block.get("type") == "tool_use" for block in assistant_blocks[0]["content"])
        )


if __name__ == "__main__":
    unittest.main()
