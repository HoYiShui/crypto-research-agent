# Crypto 投研 Agent - 项目设计

## 项目概述

一个有实时数据获取能力的 crypto 研究助手，能执行人类分析师的投研工作流中的数据密集型环节。核心价值不是"生成报告"，而是在交互式投研过程中快速响应数据查询与定量推演请求。

**竞品分析**: → [crypto_agent_competitive_analysis_v1.md](./crypto_agent_competitive_analysis.md)

## 需求分析（基于真实投研工作流）

### 工作流拆解

基于三篇实际发表的 crypto 分析文章（代币通胀分析 / 交易所风险引擎 / 投资哲学），反向提取投研流程：

```
1. 提出论点（人）
2. 寻找对比案例（人选择 + Agent 可推荐）
3. 大量数据收集与交叉验证（Agent 核心价值区）
4. 计算推演（如回购量 vs 通胀量）（Agent 可辅助）
5. 框架搭建与叙事构建（人）
6. 写作输出（人，Agent 可辅助润色）
```

### 三类投研任务与 Agent 适配度

| 任务类型 | 示例 | 数据依赖 | Agent 价值 |
|---------|------|---------|-----------|
| **定量数据分析** | 代币通胀 vs 回购量计算、跨项目数据对比 | 极高 | **核心场景** |
| **技术/产品深度拆解** | 保证金模型对比、清算机制分析 | 中等 | 辅助（文档检索+结构化对比） |
| **投资哲学思辨** | 信号与噪声、距离产生美 | 几乎无 | 不适用 |

### 市场空白（竞品验证）

所有现有产品（Kaito/AIXBT/ASCN）都做"数据聚合→展示"和"情绪/叙事监控"。**没有产品做定量推演辅助**——即"拉数据→计算→交叉验证→推导结论"的多步分析。

### MVP 核心 Tools

```
必须有（定量分析高频使用）:
1. token_unlock   → 解锁时间表、流通量变化（Tokenomist API）
2. price_market   → 价格、市值、历史走势（CoinGecko API）
3. protocol_stats → TVL、协议收入、手续费（DeFiLlama API）
4. calculator     → 回购量 vs 通胀量、稀释率等定量推演

加分项（技术分析偶尔需要）:
5. doc_reader     → 读取项目白皮书/文档，结构化提取关键信息
6. compare        → 多项目同维度对比（保证金模型、清算机制等）
```

### 典型使用场景

| 场景 | Claude 裸聊 | 本项目 Agent |
|------|-------------|-------------|
| "HYPE 的 tokenomics 风险？" | 靠训练数据泛泛而谈 | 实时拉解锁时间表 + 链上持仓集中度 → 量化评估 |
| "最近一周 Solana DEX 生态变化？" | 不知道最近数据 | 拉 DeFiLlama TVL 变化 + 链上活跃度 → 数据驱动回答 |
| "对比 Hyperliquid 和 dYdX" | 泛泛的定性对比 | 实时数据对比表 + 各维度评分 |
| "JUP 回购能对抗通胀吗？" | 概念性回答 | 拉解锁数据 + 回购金额 → 计算通胀 vs 通缩 → 定量结论 |

## 数据源 & API

### 链上数据
- **Etherscan**（免费，需 API key）: 50+ EVM 链，实时钱包数据、交易历史、合约详情
- **Dune Analytics**（免费）: SQL 查询接口，100+ 区块链，流式数据
- **DeFiLlama**（免费公开 API）: TVL、协议指标、跨链 DeFi 数据 https://api-docs.defillama.com/

### 行情数据
- **CoinGecko**（免费 Demo 层）: 30 次/分钟，10000 次/月，追踪 30M+ token https://docs.coingecko.com
- **CoinMarketCap**（免费层）: 基本面数据、白皮书链接
- **CoinDesk API**: 实时 & 历史数据、社交洞察

### 社区/舆情数据
- **Twitter/X API**: 免费层已取消，最低 $100/月。替代方案：TwitterAPI.io ($0.15/1000 推文)
- **Reddit API**（免费，有频率限制）
- **TradingVibe**（免费层）: BTC/ETH/SOL 的实时舆情 https://tradingvibe.io/
- **Augmento**（免费起步）: 93 种情绪分类，覆盖 X/Reddit/Bitcointalk https://augmento.ai
- **ApeWisdom**（免费）: Reddit & 4Chan 舆情追踪 https://apewisdom.io/api/

### 项目文档/白皮书
- **AllCryptoWhitepapers.com**: 3900+ 白皮书直链
- CoinGecko/CoinMarketCap 的元数据接口也提供白皮书链接

### DeFi & Token 数据
- **Tokenomist**（部分免费）: Vesting 时间表、代币解锁数据 https://tokenomist.ai/

**总结**: 大部分关键数据源有免费访问。Twitter/X 是主要成本障碍，但可通过 TradingVibe/Augmento 等免费舆情聚合 API 绕过。

## 现有开源项目

### 直接参考

| 项目 | 地址 | 特点 |
|------|------|------|
| **Sibyl** | https://github.com/nMaroulis/sibyl | 最接近的参考实现：AI agent + LLM 的 crypto 洞察与交易面板，RAG 系统，MCP server chatbot |
| **Open Deep Research** | https://github.com/langchain-ai/open_deep_research | 开源深度研究 agent，可作为 "DeepSearch for crypto" 的架构参考 |
| **OpenAlice** | https://github.com/TraderAlice/OpenAlice | 文件驱动 AI 交易 agent，多账户架构 |
| **LLM_Trader** | https://github.com/qrak/LLM_trader | Vision AI + 记忆增强推理 + 实时监控 |

### 成功项目的共同模式
1. Multi-agent 架构（不同分析领域由专门 agent 负责）
2. Memory/上下文管理
3. RAG 集成（白皮书、文档的本地知识库）
4. 多 API 实时数据聚合
5. MCP server 模式做 tool 集成

## 技术挑战

### 数据聚合
- **Rate Limiting**: 多个免费 API 有严格限制（CoinGecko 30/min）→ 需要请求队列、缓存层
- **数据不一致**: 不同 API 报价/TVL 可能不同 → 多源验证、时间戳追踪
- **实时 vs 历史**: 免费 API 有 5-30 分钟延迟 → 接受延迟或混合使用 Dune 实时查询

### RAG 知识库
- 白皮书是半结构化 PDF，图表多 → 需要文档切分 + 表格元数据提取
- 白皮书不反映当前状态 → 混合方案：白皮书做基础，实时 API 做当前状态
- 跨源一致性 → 实体链接（统一 "Uniswap" 在不同来源的指代）

### 推荐架构
```
Data Layer:
  - Dune SQL queries (链上数据)
  - CoinGecko cache (5-min TTL)
  - 舆情 API buffer

RAG Layer:
  - GraphRAG (白皮书实体关系)
  - Vector DB (自然语言 Q&A)

Agent Layer:
  - LLM + MCP servers
  - 专门 agent: tokenomics / 链上指标 / 社区 / 风险

Output:
  - Markdown 研究报告 + JSON 结构化数据
```

## 差异化机会（竞品验证后更新）

1. **定量推演辅助是市场空白** — Kaito/AIXBT/ASCN 都做数据聚合和情绪监控，没有产品能辅助多步定量分析（如回购 vs 通胀计算）。这是本项目的核心差异化
2. **研究导向而非交易信号** — 定位为"投研分析师助手"，不是交易 bot
3. **MCP Server 集成** — 构建可复用的 CoinGecko/DeFiLlama/Tokenomist MCP tools
4. **来源引用 + 可验证输出** — 借鉴 Kaito Pro 的 citation 机制，所有数据回答附带来源和时间戳
5. **GraphRAG（Phase 2）** — 构建 Project → Team → Holdings → Funding → Competitors 的关系图

## 与个人背景的契合

- 6 年交易经验 + Backpack Exchange 深度分析 → 真实领域知识，对交易所架构和代币经济学有分析师级理解
- 已发表的三篇文章直接作为需求来源：定量分析中的数据查询和计算环节就是 agent 要解决的问题
- 能从业务理解出发设计 agent（"为什么这个 tool 要这样设计"），而非只做技术堆砌
- 面试叙事清晰："通用 LLM 无法做实时数据查询和多步定量推演 → 我设计了专用 tool 体系和分析工作流来解决"

## 风险评估

| 风险 | 严重度 | 缓解措施 |
|------|--------|---------|
| 免费 API 限制太紧 | 中 | 缓存 + 多源轮询 + 接受延迟 |
| Twitter 数据获取成本 | 中 | 用 TradingVibe/Augmento 等聚合 API 替代 |
| 项目范围过大 | 高 | MVP 先做 1-2 个 token 的分析流程 |
| 与 Sibyl 等现有项目重复 | 中 | 聚焦差异化点（定量推演辅助，竞品无此功能） |
| 与商业产品（Kaito/ASCN）差距大 | 低 | 项目目标是实习作品，不是商业产品。展示工程能力即可 |

## 参考链接

- [Sibyl](https://github.com/nMaroulis/sibyl)
- [Open Deep Research](https://github.com/langchain-ai/open_deep_research)
- [DeFiLlama API](https://api-docs.defillama.com/)
- [CoinGecko API](https://docs.coingecko.com)
- [GraphRAG 解释](https://medium.com/@zilliz_learn/graphrag-explained-enhancing-rag-with-knowledge-graphs-3312065f99e1)
- [Crypto 知识图谱论文](https://arxiv.org/html/2502.10453v1)
