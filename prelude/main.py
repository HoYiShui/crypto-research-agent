"""
main.py: Chat entry point

Usage:
    python main.py                    # Interactive mode
    python main.py --query <text>   # Single query
"""
import argparse
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import sys

# Load .env file
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from agent.agent_loop import create_agent
from embedders.embedding_pipeline import create_embedding_pipeline


def load_crawl_config() -> dict:
    config_path = Path(__file__).parent / ".crawl_config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_embedding_model(config: dict) -> str:
    return (
        os.getenv("EMBEDDING_MODEL")
        or config.get("model")
        or "BAAI/bge-m3"
    )


def load_vectorstore(persist_dir: str = None, model_name: str = None):
    """Load existing vectorstore"""
    if not persist_dir:
        persist_dir = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
    pipeline = create_embedding_pipeline(model_name=model_name or "BAAI/bge-m3", persist_dir=persist_dir)
    return pipeline


def chat_loop(agent, vectorstore_dir: str):
    """Interactive chat loop"""
    print("=" * 60)
    print("Crypto Research Agent (Prelude)")
    print("RAG-powered crypto protocol research assistant")
    print("Using Anthropic SDK + MiniMax")
    print("=" * 60)
    print()

    # Check if vectorstore exists
    vectorstore_path = Path(vectorstore_dir)
    if not vectorstore_path.exists():
        print("[WARNING] Vectorstore not found!")
        print(f"  Expected path: {vectorstore_path}")
        print("  Run 'python scripts/build_index.py' first to build the index")
        print()

    agent.run()


def single_query(agent, query: str):
    """Single query"""
    response = agent.chat(query)
    print(response)


def main():
    parser = argparse.ArgumentParser(description="Crypto Research Agent")
    parser.add_argument(
        "--query",
        type=str,
        help="Single query to run (instead of interactive mode)"
    )
    parser.add_argument(
        "--vectorstore",
        type=str,
        default=None,
        help="Path to vectorstore directory (default: from .env or ./data/vectorstore)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="API Key (or set ANTHROPIC_AUTH_TOKEN env var)"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        help="API Base URL (or set ANTHROPIC_BASE_URL env var)"
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Model name (or set MODEL env var)"
    )

    args = parser.parse_args()

    # Load vectorstore
    print("Loading vectorstore...")
    try:
        crawl_config = load_crawl_config()
        embedding_model = resolve_embedding_model(crawl_config)
        vectorstore_dir = args.vectorstore or os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
        vectorstore = load_vectorstore(vectorstore_dir, model_name=embedding_model)
        print(f"[OK] Vectorstore loaded: {vectorstore_dir} (model={embedding_model})")
    except Exception as e:
        print(f"[WARNING] Failed to load vectorstore: {e}")
        vectorstore = None

    # Create agent
    agent = create_agent(vectorstore=vectorstore)

    # Override from CLI args
    if args.api_key:
        agent.api_key = args.api_key
        agent.client.api_key = args.api_key
    if args.base_url:
        agent.base_url = args.base_url
        agent.client.base_url = args.base_url
    if args.model:
        agent.model = args.model

    # Run
    if args.query:
        single_query(agent, args.query)
    else:
        chat_loop(agent, vectorstore_dir=vectorstore_dir)


if __name__ == "__main__":
    main()
