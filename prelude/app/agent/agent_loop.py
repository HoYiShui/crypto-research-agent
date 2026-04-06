"""
agent_loop.py: Minimal Agent Loop (~500 lines)

Core logic (based on learn-claude-code):
while True:
    response = llm.chat(messages + [user_input])
    if response.stop_reason == "tool_use":
        for tool_call in response.tool_calls:
            result = handlers.execute(tool_call.name, tool_call.input)
            messages.append(tool_result(tool_call.id, result))
    else:
        return response.content
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

try:
    import anthropic
except ImportError as e:
    raise SystemExit("Please install dependency: anthropic") from e

from app.agent.tools import TOOL_DEFINITIONS, ToolHandlers
from app.agent.system_prompt import SYSTEM_PROMPT


class MinimalAgent:
    """
    Minimal Agent Loop

    Based on learn-claude-code's minimalist agent implementation:
    - Single agent loop
    - Function calling / tool use
    - Message history management

    Uses Anthropic SDK + MiniMax
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        system_prompt: str = SYSTEM_PROMPT,
        vectorstore=None,
        vectorstore_loader=None,
        on_tool_call=None,
        on_tool_result=None,
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("MINIMAX_API_KEY")
        self.base_url = base_url or os.getenv("ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic"
        self.model = model or os.getenv("MODEL") or "MiniMax-M2.7"
        self.system_prompt = system_prompt

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        # Callbacks for bridge/TUI (optional)
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result

        # Initialize tool handlers
        self.tool_handlers = ToolHandlers(
            vectorstore=vectorstore,
            vectorstore_loader=vectorstore_loader,
        )

        # Message history
        self.messages = []

        # Interactive mode flag
        self.interactive = False

    def set_vectorstore(self, vectorstore):
        """Set vectorstore for RAG search"""
        self.tool_handlers.set_vectorstore(vectorstore)

    def set_vectorstore_loader(self, vectorstore_loader):
        """Set lazy loader for vectorstore."""
        self.tool_handlers.set_vectorstore_loader(vectorstore_loader)

    def reset(self):
        """Reset message history"""
        self.messages = []

    def chat(self, user_input: str, max_turns: int = 20) -> str:
        """
        Single conversation turn

        Args:
            user_input: User input
            max_turns: Max tool calls (prevent infinite loops)

        Returns:
            str: LLM final response
        """
        # Add user message
        self.messages.append({
            "role": "user",
            "content": user_input
        })

        turn_count = 0
        while turn_count < max_turns:
            turn_count += 1

            # Call LLM
            response = self._call_llm()

            # Check stop_reason
            if response.stop_reason != "tool_use":
                # LLM direct reply, done
                assistant_message = self._extract_text_response(response.content)
                self.messages.append({
                    "role": "assistant",
                    "content": assistant_message
                })
                return assistant_message

            # Preserve assistant tool_use message in history (required by Anthropic protocol)
            self.messages.append({
                "role": "assistant",
                "content": self._serialize_content_blocks(response.content),
            })

            # Handle tool_calls
            for tool_use in response.content:
                if tool_use.type != "tool_use":
                    continue

                tool_name = tool_use.name
                tool_input = tool_use.input

                print(f"\n[TOOL] Calling: {tool_name}")
                print(f"  Args: {tool_input}")

                if self.on_tool_call:
                    self.on_tool_call(tool_name, tool_input)

                # Execute tool
                result = self.tool_handlers.execute(tool_name, tool_input)
                print(f"  Result: {str(result)[:200]}...")

                if self.on_tool_result:
                    self.on_tool_result(tool_name, str(result))

                # Add tool result to messages
                self.messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": str(result)[:2000],
                    }]
                })

        return "Error: Max turns exceeded (possible infinite loop)"

    def _serialize_content_blocks(self, content_blocks) -> list[dict]:
        """Convert SDK content blocks to plain dicts for message history."""
        serialized = []
        for block in content_blocks:
            if hasattr(block, "model_dump"):
                serialized.append(block.model_dump(exclude_none=True))
            elif hasattr(block, "to_dict"):
                serialized.append(block.to_dict())
            elif isinstance(block, dict):
                serialized.append(block)
            else:
                block_dict = {}
                for key in ("type", "id", "name", "input", "text"):
                    if hasattr(block, key):
                        block_dict[key] = getattr(block, key)
                if block_dict:
                    serialized.append(block_dict)
        return serialized

    def _extract_text_response(self, content_blocks) -> str:
        """Extract all text blocks from assistant response."""
        texts = []
        for block in content_blocks:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type == "text":
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                if text:
                    texts.append(text)
        if texts:
            return "\n".join(texts)
        return "No response text returned."

    def _call_llm(self):
        """Call LLM using Anthropic API"""
        try:
            response = self.client.messages.create(
                model=self.model,
                system=self.system_prompt,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.7,
                max_tokens=4096,
            )
            return response
        except Exception as e:
            return type('Response', (), {
                'stop_reason': 'error',
                'content': [
                    type('Content', (), {
                        'type': 'text',
                        'text': f"Error: {str(e)}"
                    })()
                ]
            })()

    def run(self):
        """Run in interactive mode"""
        self.interactive = True
        print("=" * 60)
        print("Minimal Agent (Prelude)")
        print("Using Anthropic SDK + MiniMax")
        print("Type 'exit' or 'quit' to end the conversation")
        print("=" * 60)

        while True:
            try:
                user_input = input("\n> ")
                if user_input.lower() in ["exit", "quit", "q"]:
                    print("Goodbye!")
                    break
                if not user_input.strip():
                    continue

                response = self.chat(user_input)
                print(f"\nAgent: {response}")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")


def create_agent(vectorstore=None) -> MinimalAgent:
    """Factory function to create agent"""
    return MinimalAgent(vectorstore=vectorstore)


if __name__ == "__main__":
    agent = create_agent()
    agent.run()
