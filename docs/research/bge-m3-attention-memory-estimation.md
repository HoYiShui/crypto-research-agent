# BGE-M3 Attention Memory Estimation (Beginner-Friendly)

This note explains why we saw:

```text
RuntimeError: Invalid buffer size: 62.38 GiB
```

during embedding with `BAAI/bge-m3`.

## 1) Why Transformer memory can explode

For self-attention, one key intermediate tensor has shape:

- batch size (`B`)
- attention heads (`H`)
- query length (`L`)
- key length (`L`)

So the element count is proportional to `B * H * L * L`.
That `L * L` term is the important part: sequence length grows linearly, but attention memory grows quadratically.

## 2) Quick estimation formula

A practical approximation for one large attention buffer is:

$$
\text{bytes} \approx B \times H \times L^2 \times s
$$

where:

- $B$: batch size
- $H$: number of attention heads
- $L$: sequence length in tokens (after padding)
- $s$: bytes per element (`float32 = 4`)

Convert to GiB with:

$$
\text{GiB} = \frac{\text{bytes}}{1024^3}
$$

## 3) Plug in our case

From our runtime stack:

- `SentenceTransformer.encode` default batch size is `32`
- `bge-m3` config has `num_attention_heads = 16`
- dtype in config is `float32` (`s = 4`)

Given the observed error `62.38 GiB`, reverse solve for $L$:

$$
L \approx \sqrt{\frac{62.38 \times 1024^3}{32 \times 16 \times 4}} \approx 5719
$$

So a batch padded to around `~5.7k tokens` is enough for that single buffer to reach about `62 GiB`.

## 4) Why this can happen even if only some chunks are huge

`encode` works by batches. In each batch, shorter samples are padded to the longest sample.
That means one very long chunk can increase memory cost for the entire batch.

In our pipeline, oversized chunks came from large sections (tables/legal/spec pages), which made this scenario likely.

## 5) Why this estimate is approximate (but useful)

This formula is not the full model memory footprint. Real peak memory is affected by:

- multiple intermediate tensors (Q/K/V, residual activations, temp buffers)
- kernel implementation details (e.g., SDPA internals)
- extra framework overhead

So `62.38 GiB` is best read as: one large internal allocation hit this size class, consistent with long-sequence attention pressure.

## 6) Practical implications for RAG indexing

To avoid this failure class:

1. hard-cap chunk token length for all block types (not only plain text)
2. reduce embedding batch size
3. optionally truncate max sequence length during embedding
4. remove low-value duplicate pages (e.g., revision mirrors)

These controls directly reduce either $L$ or $B$, which is exactly what the formula says to do.
