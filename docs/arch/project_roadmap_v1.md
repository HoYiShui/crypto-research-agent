# Crypto 投研 Agent - 项目路线图

## 开发顺序（架构演进路径）

### Phase 1: RAG 知识库管道
**目标**：构建"信息获取"的基础设施，让 agent 有知识支撑

- [ ] 白皮书、链上数据、实时行情的数据源接入
- [ ] Semi-structured PDF 处理与文档切分
- [ ] 向量存储选型（Pinecone/LanceDB/Chroma）
- [ ] GraphRAG 实体关系构建

**技术要点**：
- 数据源：AllCryptoWhitepapers（白皮书）、Dune/Etherscan（链上）、CoinGecko（行情）
- 文档切分：PDF 表格元数据提取、半结构化处理
- 向量库：Chroma（本地开发）/ Pinecone（生产）
- RAG 框架：LangChain 或 LlamaIndex

---

### Phase 2: 数据分析工具
**目标**：让 agent 有计算能力，不只是嘴炮

- [ ] 代码执行能力（Python REPL / Jupyter kernel）
- [ ] DB 连接（SQLite/PostgreSQL，企业内部数据库）
- [ ] 二次处理与可视化输出

**技术要点**：
- 代码执行：E2B / Copilot Labs 方案，或自建 Python sandbox
- DB 连接：SQLAlchemy + 主流数据库驱动
- 可视化：Matplotlib/Plotly 生成图表，Markdown 内嵌

---

### Phase 3: Multi-Agent 系统
**目标**：定义不同角色 agent，把工具抽象成 CLI/MCP 供其使用

- [ ] Agent 角色定义（tokenomics / 链上指标 / 社区 / 风险）
- [ ] 工具抽象为 CLI 和 MCP
- [ ] Agent 间协作与路由机制

**技术要点**：
- 架构模式：Hub-and-Spoke / Hierarchy / Swarm
- Agent 定义：角色职责、工具边界、消息协议
- 编排层：任务分解、结果聚合、冲突解决

---

### Phase 4: 记忆机制
**目标**：让系统有"记忆"，不每次从零开始

- [ ] 长短期记忆设计
- [ ] 经验复用（类似 OpenClaw / MemGPT）

**技术要点**：
- 短期：会话上下文窗口管理
- 长期：向量记忆存储 + 结构化记忆（实体-关系图）
- 记忆检索：基于当前任务的相关记忆召回

---

## 后续企业级扩展（非核心序列）

| 模块 | 说明 |
|------|------|
| SFT | 指令微调，针对投研场景 fine-tune 模型 |
| API 抽象层 | FastAPI 封装，REST/WebSocket 接口 |
| Docker 部署 | 容器化，模型服务 + Agent 服务分离 |
| Agent 评估 | 投研输出质量评估、RAG 效果评估 |

---

## 架构全貌

```
User Input
    │
    ▼
┌─────────────────────────────────────────┐
│            Multi-Agent Orchestration     │
│         (Agent Router + Memory)          │
└─────────────────────────────────────────┘
    │              │              │
    ▼              ▼              ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│Data     │  │  RAG    │  │Research │
│Agent    │  │ Agent   │  │ Agent   │
└─────────┘  └─────────┘  └─────────┘
    │              │              │
    └──────────────┼──────────────┘
                   ▼
        ┌─────────────────────┐
        │   工具抽象层        │
        │  CLI / MCP / API   │
        └─────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│  RAG    │  │数据分析 │  │ 记忆    │
│ 管道    │  │ 工具    │  │ 机制    │
└─────────┘  └─────────┘  └─────────┘
```

---

## 核心差异化

1. **定量推演辅助**（市场空白）：回购 vs 通胀计算、稀释率推演——不是生成报告，是交互式投研辅助
2. **定位**：投研分析师助手，不是交易 bot
3. **覆盖技术栈**：RAG + 代码执行 + Multi-Agent + 记忆机制，完整链路

---

## 项目状态

- [x] 竞品分析（`crypto_agent_competitive_analysis_v1.md`）
- [x] 项目设计（`crypto_research_agent_v1.md`）
- [x] 项目路线图（本文档）
- [ ] Phase 1: RAG 知识库管道 ← 当前阶段
- [ ] Phase 2: 数据分析工具
- [ ] Phase 3: Multi-Agent 系统
- [ ] Phase 4: 记忆机制
