# Vibe-Trading 项目文档

本文档面向开发、部署和二次集成人员，说明 Vibe-Trading 的功能边界、整体架构、主要模块、依赖中间件、启动方式、API 使用方式和运行数据存储。

## 文档目录

- [架构设计](./architecture.md)
- [开源依赖与中间件](./dependencies.md)
- [项目模块实现说明](./modules.md)
- [部署与启动](./deployment.md)
- [REST API 与长任务结果获取](./api.md)
- [运行数据与持久化](./data-storage.md)

## 项目定位

Vibe-Trading 是一个开源的个人交易研究智能体。它把自然语言任务连接到行情数据、文件解析、策略生成、回测、Alpha 因子评估、多智能体研究团队、交易连接器和报告产物。

项目的主要交互方式是：

```text
用户提问/下发任务 -> Agent 判断任务类型 -> 调用工具/数据/回测/Swarm -> 产出结果和 artifacts
```

## 核心能力

- 自然语言金融研究和问答。
- 跨市场数据加载与策略回测。
- Alpha Zoo 因子浏览、评测和对比。
- 多智能体 Swarm 研究团队。
- Shadow Account 交易行为复盘。
- 文件、网页、交易流水读取与分析。
- CLI、Web UI、REST API、MCP 多入口。
- 实盘/模拟交易连接器，带 mandate、kill switch 和审计账本。
- 跨 session 持久记忆和可扩展 skills。

## 技术栈摘要

- 后端：Python 3.11+、FastAPI、LangChain、LangGraph、Pydantic。
- 前端：React 19、Vite、TypeScript、Zustand、ECharts。
- 数据分析：Pandas、NumPy、SciPy、DuckDB、scikit-learn。
- 行情源：yfinance、AKShare、Tushare、CCXT、OKX、Futu、mootdx 等。
- 协议与集成：REST、SSE、MCP。
- 存储：文件系统、JSON/JSONL、SQLite FTS5、Parquet/Pickle 缓存。

## 常用入口

```bash
# Docker 启动 Web/API
docker compose up -d

# Docker 内执行同步 CLI 长任务
docker compose exec vibe-trading \
  vibe-trading run -p "帮我回测 BTC-USDT 2024 年 20/50 均线策略"

# 本地开发启动 API
vibe-trading serve --port 8899

# 本地启动 CLI
vibe-trading

# MCP Server
vibe-trading-mcp
```

