"""
tools.py: Agent Tools Definitions and Handlers
"""
import json
import subprocess
from pathlib import Path
from typing import Callable, Any


# ============================================
# Tool Definitions (for LLM)
# ============================================

TOOL_DEFINITIONS = [
    {
        "name": "rag_search",
        "description": "Search the crypto documentation knowledge base. Use this to find information about crypto protocols, trading fees, tokenomics, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query about crypto protocols, fees, tokenomics, etc."
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "bash",
        "description": "Execute a bash command in the terminal. Use for running scripts, git commands, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file from the filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to read"
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of lines to read from the start. If not specified, reads entire file.",
                    "default": 100
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Creates the file if it doesn't exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file"
                }
            },
            "required": ["path", "content"]
        }
    },
]


# ============================================
# Tool Handlers (actual execution)
# ============================================

class ToolHandlers:
    """Tool Handlers container"""

    def __init__(self, vectorstore=None, vectorstore_loader: Callable[[], Any] | None = None):
        self.vectorstore = vectorstore
        self.vectorstore_loader = vectorstore_loader
        self._handlers = {
            "rag_search": self._rag_search,
            "bash": self._bash,
            "read_file": self._read_file,
            "write_file": self._write_file,
        }

    def set_vectorstore(self, vectorstore):
        """Set vectorstore (for rag_search)"""
        self.vectorstore = vectorstore

    def set_vectorstore_loader(self, vectorstore_loader: Callable[[], Any] | None):
        """Set lazy loader for vectorstore."""
        self.vectorstore_loader = vectorstore_loader

    def get_handler(self, tool_name: str) -> Callable:
        """Get handler by name"""
        return self._handlers.get(tool_name)

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute tool"""
        handler = self.get_handler(tool_name)
        if not handler:
            return f"Error: Unknown tool '{tool_name}'"

        try:
            result = handler(**tool_input)
            return result
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def _rag_search(self, query: str, top_k: int = 5) -> str:
        """RAG search"""
        if self.vectorstore is None and self.vectorstore_loader is not None:
            try:
                self.vectorstore = self.vectorstore_loader()
            except Exception as e:
                return (
                    "RAG_UNAVAILABLE: Failed to initialize vectorstore lazily: "
                    f"{str(e)}. Do not answer from memory; ask user to retry or fix index/model config."
                )

        if self.vectorstore is None:
            return (
                "RAG_UNAVAILABLE: Vectorstore not initialized. "
                "Build index and verify embedding model availability. "
                "Do not answer from memory."
            )

        try:
            results = self.vectorstore.search(query=query, k=top_k)

            if not results:
                return "No results found."

            output = []
            for i, (doc, score) in enumerate(results, 1):
                output.append(f"[{i}] Score: {score:.4f}")
                output.append(f"    Source: {doc.metadata.get('source_url', 'unknown')}")
                output.append(f"    Path: {doc.metadata.get('heading_path', 'unknown')}")
                output.append(f"    Content:\n{doc.page_content[:500]}")
                if len(doc.page_content) > 500:
                    output.append("    ...")
                output.append("")

            return "\n".join(output)
        except Exception as e:
            return (
                f"RAG_UNAVAILABLE: RAG search error: {str(e)}. "
                "Do not answer from memory; report retrieval failure."
            )

    def _bash(self, command: str) -> str:
        """Execute bash command"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(f"STDERR: {result.stderr}")
            if result.returncode != 0 and not result.stdout and not result.stderr:
                output.append(f"Command exited with code {result.returncode}")
            return "\n".join(output)[:2000]
        except subprocess.TimeoutExpired:
            return "Error: Command timed out (30s limit)"
        except Exception as e:
            return f"Error: {str(e)}"

    def _read_file(self, path: str, lines: int = 100) -> str:
        """Read file"""
        try:
            p = Path(path)
            if not p.exists():
                return f"Error: File not found: {path}"

            content = p.read_text()
            content_lines = content.split('\n')

            if lines and lines < len(content_lines):
                content = '\n'.join(content_lines[:lines])
                return f"[Showing first {lines} lines of {len(content_lines)} total]\n\n{content}"
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def _write_file(self, path: str, content: str) -> str:
        """Write file"""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Successfully wrote to {path} ({len(content)} bytes)"
        except Exception as e:
            return f"Error writing file: {str(e)}"


# Format tool result for LLM
def tool_result(tool_use_id: str, content: str) -> dict:
    """Format tool execution result as LLM message"""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": content,
            }
        ]
    }
