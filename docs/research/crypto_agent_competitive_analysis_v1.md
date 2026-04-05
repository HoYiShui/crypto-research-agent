# Crypto 投研 Agent - 竞品分析

> 调研日期：2026-03-09

## 竞品概览

|          | **Kaito**                              | **AIXBT**                    | **ASCN.AI**                | **Jenova**              |
| -------- | -------------------------------------- | ---------------------------- | -------------------------- | ----------------------- |
| **定位**   | Crypto 信息搜索引擎 ("Bloomberg for crypto") | 自主叙事分析 agent                 | Crypto 专用 AI 分析师           | 通用 AI 平台（非 crypto 垂类）   |
| **团队**   | Yu Hu, ex-Citadel                      | 匿名 "Rxbt", Virtuals Protocol | ArbitrageScan 团队, UAE      | Boris Wang, ex-Apple PM |
| **融资**   | $10.8M (Dragonfly, 红杉中国, Jane Street)  | 无传统融资，token 驱动               | 不详                         | 不详                      |
| **年化营收** | >$35M                                  | token 收入（buyback-burn）       | 不详                         | 不详                      |
| **产品形态** | Web dashboard + API                    | X 自主发帖 + Terminal 面板         | Web chatbot + API + TG bot | 多模型 chatbot + app 平台    |
| **价格**   | $833/mo (Pro)                          | $200/mo 或持 60万 AIXBT         | $29-299/mo                 | Free / $20-200/mo       |

## 详细分析

### 1. Kaito.ai — 信息搜索引擎

**核心产品**:
- **Kaito Pro** (B2B, $833/mo): 面向机构的搜索+分析 dashboard，700+ 专业团队使用
  - AI chatbot（项目概述、研发动态、多空论点汇总，带来源引用）
  - Metasearch（跨 X/Discord/TG/播客/治理论坛的统一搜索）
  - Mindshare 量化指标（项目注意力份额 + 情绪追踪）
  - 实时告警（自定义条件 → TG/Email/API 推送）
- **Kaito Connect/Studio** (B2C, 免费/token-gated): InfoFi 社交层，原 Yaps 产品（1M 用户，2026.01 因 X 封禁已下线），转型为 Studio（品牌-创作者匹配平台）

**数据源**: X/Discord/TG/播客全量爬取 + 治理论坛 + 新闻 + 正在集成链上数据

**技术架构** (公开信息):
```
Crawlers → Amazon Kinesis (实时流) + S3 (备份)
              ↓
         RisingWave (流处理数据仓库)
         - 数据清洗/富化/聚合
         - Materialized Views
              ↓
    OpenSearch (全文检索) + Kinesis→Lambda (实时告警) + 1000+ 分析 Dashboard
```

**Moat**: 全量社交数据爬取基础设施 + Mindshare 指标的行业标准地位 + 网络效应

### 2. AIXBT — 自主 AI Agent

**核心产品**:
- **X 公开 bot** (@aixbt_agent, 450K+ 粉丝): 99% 自主，24/7 发布市场分析推文
- **AIXBT Terminal** ($200/mo 或 token-gated): 无限 Q&A + 项目评级 + 交易信号 + 鲸鱼追踪

**数据源**: 400+ crypto KOL 监控 + CoinGecko + DeFiLlama + BubbleMaps + 社交平台

**技术**: Virtuals Protocol GAME 框架（Agent Commerce Protocol），前端 Next.js

**关键数据点**:
- **Token calls 准确率仅 31%**
- Token 从 ATH $0.95 跌至 ~$0.023（-97%）
- 更像 KOL 而非分析工具，其推文本身能影响市场（Mog Coin 提及后涨 18%）

### 3. ASCN.AI — Crypto 专用 AI 分析师

**核心产品**:
- 浏览器 chatbot + API + TG bot
- Token 分析、链上取证、情绪分析、融资数据库（14000+ 轮次）
- 自定义 AI agent 构建器（无代码）
- Hyperliquid 专用分析模块

**数据源**:
- **自有区块链节点**（ETH/SOL，直连 mempool）
- Dune Analytics + Messari + DeBank
- TG/X 社交平台（含私有交易社群）

**技术**: 宣称 Web3 专属训练 LLM "ASCN v1.2"，模块化插件架构，前端 Nuxt.js

**关键数据点**:
- 宣称 81% 预测准确率（不可验证）
- 起价 $29/mo，Premium $299/mo
- 注册在 UAE RAK DAO，与 ArbitrageScanner 同团队

### 4. Jenova.ai — 通用 AI 平台（非真正竞品）

**核心产品**: 通用多模型路由 AI 平台，"Crypto Analyst" 只是预置 agent 之一

**技术**: 智能模型路由（GPT-5.2/Claude Opus 4.5/Gemini 3 Pro/Grok 4.1），无专有 crypto 数据源

**Moat 评估**: 很薄。本质是 prompt 包装的通用 AI，底层数据源全公开可得。第三方评测发现 placeholder 链接、偶发幻觉等问题。

**结论**: 不算 crypto 垂类竞品，不纳入核心对标范围。

## 竞品能力矩阵

| 能力维度 | Kaito | AIXBT | ASCN | 我的项目目标 |
|---------|-------|-------|------|------------|
| 社交/舆情监控 | **极强** | 强 | 中 | 低优先级 |
| 链上数据分析 | 在建 | 弱 | **强**（自有节点）| 中（通过 API） |
| 叙事/趋势识别 | 强 | **极强** | 中 | 低优先级 |
| 定量推演辅助 | **无** | **无** | **无** | **核心差异化** |
| 代币经济学分析 | 弱 | 弱 | 中 | **核心功能** |
| 交互式问答 | 有 | 有 | 有 | 有（CLI） |
| 报告生成 | 有 | 无 | 有 | 有 |
| 多步计算推理 | **无** | **无** | **无** | **核心差异化** |

## 关键发现

### 1. 市场空白：定量推演

所有竞品都聚焦于"数据聚合 → 展示"和"情绪/叙事监控"。**没有产品**能辅助完成类似以下的多步定量分析：

> "JUP 流通从 20.25% 增至 47.51%，其中 700M 空投 + 933M 团队 + 175M Mercurial。
> 回购 $70M ÷ 价格 $0.2105 = 332M 枚。通胀增量远超回购通缩。"

这种"拉数据 → 计算 → 交叉验证 → 推导结论"的工作流，是当前 agent 产品的盲区。

### 2. 准确率普遍存疑

- AIXBT 31% 准确率（公开可查）
- ASCN 81% 准确率（自称，不可验证）
- 说明当前 crypto AI 产品更多是叙事驱动，而非真正解决分析问题

### 3. 对项目定位的启示

**不需要对标商业产品**。项目的两个目标：
1. **实习作品** → 展示 agent 工程能力（tool 设计、编排、eval），CLI chatbot 完全够用
2. **实际工具** → 辅助自己的投研，差异化在"定量推演"而非"情绪监控"

**可借鉴的模式**:
- MCP tool 集成模式（ASCN 的插件架构）
- 多源数据聚合 + 缓存（Kaito 的流处理思路，但简化为 TTL 缓存）
- 来源引用 + 可验证输出（Kaito Pro 的 citation 机制）

## 参考来源

**Kaito**:
- [SCB 10X: Kaito's AI Knowledge Engine](https://www.scb10x.com/en/blog/kaito-ai-crypto)
- [RisingWave: Real-Time Data Infrastructure at Kaito](https://risingwave.com/blog/how-risingwave-empowers-the-real-time-data-infrastructure-kaito-the-next-gen-ai-research-platform-for-web-3/)

**AIXBT**:
- [DrooomDroom: AIXBT Explained](https://droomdroom.com/aixbt-by-virtuals-explained/)
- [Decrypt: What Is AiXBT?](https://decrypt.co/299393/what-is-aixbt-ai-crypto-influencer)
- [ChainCatcher: AIXBT Performance Analysis](https://www.chaincatcher.com/en/article/2162356)

**ASCN**:
- [ASCN.AI](https://ascn.ai/)
- [CoinSpice: ASCN Dubai Event](https://coinspice.io/news/ascn-ai-crypto-analysis-dubai-gathering-2025/)
- [CoinMoi: ASCN Review](https://coinmoi.com/ascn-ai-best-ai-powered-crypto-tools-for-on-chain-analysis-and-market-insights/)

**Jenova**:
- [Jenova.ai](https://www.jenova.ai)
- [Tech-Now: Jenova vs ChatGPT](https://tech-now.io/en/blogs/jenova-ai-vs-chatgpt-features-pricing-use-cases)
