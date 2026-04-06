# RAG Pipeline Incident Log

## 2026-04-06 - BGE-m3 OOM on oversized chunks

### Symptom

`build_index.py` succeeded in crawl/parse/chunk, then failed at embedding stage:

```text
RuntimeError: Invalid buffer size: 62.38 GiB
```

The error was raised inside `sentence_transformers` / `transformers` attention forward during:

- `prelude/rag/embedders/embedding_pipeline.py`
- `self.model.encode(texts, **self.encode_kwargs)`

### Context

- Embedding model: `BAAI/bge-m3`
- Input corpus included long legal/spec pages (e.g. Terms, contract specs, large tables).
- Chunk artifacts contained very large chunks (char-level observation: max around 19k+ chars).

### Working hypothesis

This is a memory pressure issue triggered by long-sequence attention cost on large chunks, amplified by batch encoding. In practice: some chunks are too large for stable `bge-m3` embedding on current machine settings.

For step-by-step memory estimation and intuition (beginner-friendly), see:
`docs/research/bge-m3-attention-memory-estimation.md`.

### Immediate notes

- This is independent from crawl stability issues.
- Next mitigation candidates (to verify in follow-up):
  1. enforce hard max chunk size for all block types (including table/code)
  2. reduce embedding `batch_size`
  3. optionally cap `max_seq_length` and truncate during encoding
  4. filter low-value duplicate/revision pages before chunking

### Reproduction status

- Reproduced in real run after `crawl -> parse -> chunk` completed successfully.
- Failure consistently appears at Step 4 embedding for the current dataset profile.
