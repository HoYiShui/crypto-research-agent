# 2026-04-06 RAG Grounding 问题记录（Prelude）

## 背景
- 来源：一次真实对话中，用户询问“如果只能选一个 Hyperliquid 特性来说服我去交易，会是什么”。
- 观察：Agent 触发了 3 次 `rag_search`，但最终回答与当次检索证据绑定不够强，存在“可读但可能过度归纳”的风险。

## 复现输入（用户原始记录）
```text
crypto-dyor-assistant/prelude on  main [?] is 📦 v0.1.0 via 🐍 v3.14.3
❯ uv run python main.py
Loading vectorstore...
Loading weights: 100%|█████████████████████████████████| 103/103 [00:00<00:00, 5501.88it/s]
BertModel LOAD REPORT from: /Users/hoyishui/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/c9745ed1d9f207416be6d2e6f8de32d1f16199bf
Key                     | Status     |  |
------------------------+------------+--+-
embeddings.position_ids | UNEXPECTED |  |

Notes:
- UNEXPECTED:   can be ignored when loading from different task/architecture; not ok if you expect identical arch.
[OK] Vectorstore loaded: ./data/vectorstore (model=sentence-transformers/all-MiniLM-L6-v2)
============================================================
Crypto Research Agent (Prelude)
RAG-powered crypto protocol research assistant
Using Anthropic SDK + MiniMax
============================================================

============================================================
Minimal Agent (Prelude)
Using Anthropic SDK + MiniMax
Type 'exit' or 'quit' to end the conversation
============================================================

> hello?

Agent: Hello! How can I help you today? I'm here to assist with researching crypto protocols, looking up trading fees, tokenomics, protocol features, and other blockchain-related information.

Feel free to ask me anything!

> if you need to pick up only one trait about hyperliquid to presue me to trading in hyperliquid instead of other exchange, what would be that?

[TOOL] Calling: rag_search
  Args: {'query': 'Hyperliquid unique features advantages differentiating from other exchanges', 'top_k': 5}
  Result: [1] Score: 0.4854
    Source: hypercore/aligned-quote-assets
    Path: ['Aligned quote assets']
    Content:
[Aligned quote assets]
Aligned quote assets

[Aligned quote assets]
The Hyperliquid protoco...

[TOOL] Calling: rag_search
  Args: {'query': 'Hyperliquid L1 blockchain decentralized exchange perp trading key features', 'top_k': 5}
  Result: [1] Score: 0.4220
    Source: hypercore/aligned-quote-assets
    Path: ['Aligned quote assets']
    Content:
[Aligned quote assets]
Aligned quote assets

[Aligned quote assets]
The Hyperliquid protoco...

[TOOL] Calling: rag_search
  Args: {'query': 'Hyperliquid permissionless decentralized trading competitive fees speed', 'top_k': 5}
  Result: [1] Score: 0.4139
    Source: about-hyperliquid/hyperliquid-101-for-non-crypto-audiences
    Path: ['Hyperliquid 101 for non-crypto audiences']
    Content:
[Hyperliquid 101 for non-crypto audiences]
...

Agent: Based on my research of the Hyperliquid documentation, if I had to pick **one key trait** to persuade you to trade on Hyperliquid instead of other exchanges, it would be:

## **It's a Purpose-Built L1 Blockchain Optimized for Trading**

Hyperliquid is not just another exchange or a dApp on another chain — it's a **Layer 1 blockchain written and optimized from first principles** for high-performance trading and perpetual futures.

### Why this matters:

1. **Performance** — Custom consensus algorithm (HyperBFT) designed specifically for fast transaction finality and low latency

2. **Cost Efficiency** — Being the base layer means cheaper fees compared to trading on smart contract platforms where you pay gas on top of trading fees

3. **Deep Integration** — Liquidity, trading activity, and user applications all synergize on a unified platform, creating better liquidity and tighter spreads

4. **Transparency & Decentralization** — As a purpose-built blockchain, it offers the security and openness of onchain infrastructure rather than opaque centralized systems

---

**In short**: Hyperliquid is designed *from the ground up* for trading, not retrofitted onto a general-purpose blockchain. This gives it the speed, costs, and ecosystem cohesion that general L1s or centralized exchanges can't match.

Would you like me to dive deeper into any specific aspect — like fees, supported trading pairs, or technical details?

> ^C

Goodbye!
```

## 复现步骤（最小）
1. 在 `prelude/` 目录执行：`uv run python main.py`
2. 第一轮输入：`hello?`
3. 第二轮输入：`if you need to pick up only one trait about hyperliquid to presue me to trading in hyperliquid instead of other exchange, what would be that?`
4. 观察控制台中是否出现连续 3 次 `rag_search`，并检查 top1 是否仍可能命中 `hypercore/aligned-quote-assets`
5. 记录最终回答是否明显超出检索片段可直接支持的范围

## 已确认现象
- 向量库可用，非“没索引/没数据”问题。
- 检索可返回结果，但 top 命中不稳定，容易命中边缘主题（如 `aligned-quote-assets`）。
- 结果展示中的 `Score` 实际是 distance（越小越相关），命名会误导判断。
- `source_url` 当前为相对路径，引用可读性与可验证性不足。
- tool result 传回模型时有截断（2000 字符），会损失证据上下文。
- 当前 system prompt 只要求“先检索”，没有硬性约束“必须基于检索证据回答”。

## 证据（代码定位）
- 距离被当作 score 展示：`prelude/embedders/embedding_pipeline.py:176` + `prelude/agent/tools.py:155`
- tool result 截断：`prelude/agent/agent_loop.py:159`
- parser 直接对整页 HTML 做 markdownify（噪声风险）：`prelude/parsers/html_to_markdown.py:166`
- block.source_url 写入 page["url"]（当前索引里多为相对路径）：`prelude/scripts/build_index.py:170`
- prompt 仅要求先查 RAG，无强 grounding 约束：`prelude/agent/system_prompt.py:31`

## 数据检查结果（本地）
- `data/raw_html` 页面数：`104`
- `data/vectorstore` 文档数：`685`
- `source_url` 分布：绝对 URL `0`，相对路径 `685`，空值 `0`

## 优先级建议（按影响排序）
1. Grounding 约束：回答必须引用 top 命中片段；低相关时明确“不足以下结论”。
2. 检索输出语义修正：将 `Score` 改为 `Distance` 或转换为可解释相似度。
3. 引用可验证性：统一存储 canonical absolute URL。
4. 上下文完整性：提高或分段传递 tool_result，避免 2000 字符硬截断。
5. 降噪：在 HTML -> Markdown 前增加主内容提取，减少导航/锚点污染。

## 可执行 TODO（下一步）
- [ ] `prelude/agent/tools.py`：调整检索结果展示字段（distance/similarity）并补充命中质量提示。
- [ ] `prelude/agent/system_prompt.py`：增加“证据不足时拒答/降级回答”的硬规则。
- [ ] `prelude/agent/agent_loop.py`：评估 tool_result 截断策略（上限、分块、摘要+原文混合）。
- [ ] `prelude/scripts/build_index.py`：写入 absolute canonical `source_url`。
- [ ] `prelude/parsers/html_to_markdown.py`：评估主内容抽取方案后再 markdownify。
