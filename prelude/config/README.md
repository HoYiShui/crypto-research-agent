# Source Registry (`craw_list.json`)

`craw_list.json` describes crawl sources for `scripts/build_index.py`.
It is a source registry (what to crawl), not runtime model config.

## Schema

```json
{
  "max_page": 50,
  "site": [
    {
      "name": "hyperliquid",
      "type": "gitbook",
      "base_url": "https://hyperliquid.gitbook.io/hyperliquid-docs/",
      "enable": true
    }
  ]
}
```

## Fields

- `max_page` (required, integer > 0): max pages per enabled site.
- `site` (required, array): list of crawl targets.

Each `site[]` object:
- `name` (required, non-empty string): site label and raw HTML subdirectory name (`data/raw_html/<name>/`).
- `type` (required, non-empty string): crawler type. Current supported value: `gitbook`.
- `base_url` (required, non-empty string): crawl entry URL.
- `enable` (required, boolean): whether this site is included in the build.

## Recommended Command

```bash
python scripts/build_index.py --rebuild
```

For stage-rebuild and overrides, run `python scripts/build_index.py --help` or read the script docstring.

---

# Pipeline Defaults (`rag_pipeline.yaml`)

`rag_pipeline.yaml` stores shared RAG pipeline defaults (chunking and embedding behavior).

Current keys:
- `crawl.default_max_page`: fallback crawl page cap when `craw_list.json` does not define `max_page`.
- `chunking.max_tokens_per_chunk`: hard token budget per chunk.
- `chunking.warn_tokens_per_chunk`: warning threshold (diagnostic use).
- `embedding.model`: default embedding model id.
- `embedding.batch_size`: embedding encode batch size.
- `embedding.max_seq_length`: max sequence length used by embedding model.
- `embedding.normalize_embeddings`: whether to normalize output vectors.
