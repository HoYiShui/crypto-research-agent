"""
Pipeline config loader for RAG defaults.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PIPELINE_CONFIG: dict[str, Any] = {
    "crawl": {
        "default_max_page": 50,
    },
    "chunking": {
        "max_tokens_per_chunk": 1024,
        "warn_tokens_per_chunk": 768,
    },
    "embedding": {
        "model": "BAAI/bge-m3",
        "batch_size": 4,
        "max_seq_length": 1024,
        "normalize_embeddings": True,
    },
}

DEFAULT_PIPELINE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "rag_pipeline.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=8)
def load_pipeline_config(config_path: str | None = None) -> dict[str, Any]:
    """
    Load rag pipeline YAML config and merge with defaults.
    """
    path = Path(config_path) if config_path else DEFAULT_PIPELINE_CONFIG_PATH
    if not path.exists():
        return deepcopy(DEFAULT_PIPELINE_CONFIG)

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to parse pipeline config {path}: {exc}") from exc

    if loaded is None:
        loaded = {}

    if not isinstance(loaded, dict):
        raise ValueError(f"Pipeline config must be a YAML object: {path}")

    return _deep_merge(DEFAULT_PIPELINE_CONFIG, loaded)


def get_crawl_config(config_path: str | None = None) -> dict[str, Any]:
    return load_pipeline_config(config_path).get("crawl", {})


def get_chunking_config(config_path: str | None = None) -> dict[str, Any]:
    return load_pipeline_config(config_path).get("chunking", {})


def get_embedding_config(config_path: str | None = None) -> dict[str, Any]:
    return load_pipeline_config(config_path).get("embedding", {})
