# 项目模块具体实现

## 顶层目录

```text
Vibe-Trading/
├── agent/                 Python 后端、CLI、API、MCP、回测和测试
├── frontend/              React Web UI
├── wiki/                  静态文档站
├── assets/                README 和站点图片资源
├── scripts/               开发脚本
├── tools/                 仓库级工具脚本
├── Dockerfile             Docker 镜像构建
├── docker-compose.yml     Docker Compose 默认配置
└── pyproject.toml         Python 包、依赖、入口点
```

## `agent/api_server.py`

FastAPI 服务入口，负责：

- 静态前端托管。
- 健康检查。
- session 创建、消息发送、SSE 事件流。
- runs 列表和详情查询。
- 文件上传。
- Swarm preset 和 run API。
- Alpha Zoo API。
- Settings 读写。
- 安全边界、认证、路径校验、本地/远程访问判断。

关键运行目录：

- `RUNS_DIR = agent/runs`
- `SESSIONS_DIR = agent/sessions`
- `UPLOADS_DIR = agent/uploads`
- `agent/.swarm/runs`

## `agent/cli/`

CLI 包，提供命令式和交互式使用。

主要能力：

- `vibe-trading`：进入交互式 TUI。
- `vibe-trading run -p "..."`：同步执行 Agent 任务。
- `vibe-trading serve --port 8899`：启动 API/Web。
- `vibe-trading resume <session_id>`：恢复历史会话。
- `vibe-trading --list` / `--show <run_id>`：查看历史 run。
- `vibe-trading --swarm-run ...`：执行 Swarm。
- `vibe-trading alpha ...`：Alpha Zoo CLI。
- `vibe-trading memory ...`：持久记忆管理。

## `agent/mcp_server.py`

MCP Server 入口，把内部工具暴露为 MCP tools。

典型工具包括：

- `backtest`
- `factor_analysis`
- `web_search`
- `read_document`
- `run_swarm`
- `get_market_data`
- `list_runs`
- `get_run_result`
- `trading_*`

适合接入 Cursor、Claude Desktop、OpenClaw 等 MCP 客户端。

## `agent/src/agent/`

Agent 核心实现。

| 文件 | 说明 |
| --- | --- |
| `loop.py` | ReAct 主循环、LLM 调用、工具批处理、run 状态、trace、取消 |
| `context.py` | 构造 system/user/tool 上下文，注入 skills 和 memory |
| `skills.py` | 加载内置和用户自建 skills |
| `tools.py` | 工具基类和工具接口 |
| `memory.py` | 单 run 工作区状态 |
| `trace.py` | 执行轨迹写入和读取 |
| `frontmatter.py` | Markdown frontmatter 解析 |

Agent 的基本执行过程：

```text
输入 prompt
  -> 构造上下文
  -> 调 LLM
  -> 解析 tool calls
  -> 执行工具
  -> 把工具结果回填给 LLM
  -> 直到产出 final answer 或达到限制
```

## `agent/src/tools/`

工具目录是 Agent 能力扩展的主入口。

重点工具：

- `backtest_tool.py`：调用回测引擎，生成指标、代码、报告产物。
- `market_data_tool.py`：统一获取行情。
- `factor_analysis_tool.py`：因子分析。
- `alpha_zoo_tool.py`、`alpha_bench_tool.py`、`alpha_compare_tool.py`：Alpha Zoo。
- `swarm_tool.py`：启动和查询多智能体团队。
- `web_search_tool.py`：免费搜索引擎聚合查询。
- `web_reader_tool.py`：网页读取。
- `doc_reader_tool.py`：PDF/Word/Excel/PPT/图片等文档读取。
- `trade_journal_tool.py`：交易流水解析。
- `shadow_account_tool.py`：Shadow Account 规则提取、回测和报告。
- `trading_connector_tool.py`：交易连接器统一入口。
- `remember_tool.py`：写入持久记忆。
- `session_search_tool.py`：跨 session 搜索。
- `read_file_tool.py`、`write_file_tool.py`、`edit_file_tool.py`：受控文件读写。

## `agent/backtest/`

回测核心。

### engines

`agent/backtest/engines/` 包含不同市场或产品的回测逻辑：

- `china_a.py`
- `china_futures.py`
- `global_equity.py`
- `global_futures.py`
- `crypto.py`
- `forex.py`
- `options_portfolio.py`
- `composite.py`

`composite.py` 用于混合市场组合回测。

### loaders

`agent/backtest/loaders/` 统一加载不同市场数据：

- `yfinance_loader.py`
- `akshare_loader.py`
- `tushare.py`
- `mootdx_loader.py`
- `ccxt_loader.py`
- `okx.py`
- `futu.py`
- `baostock_loader.py`
- `rsshub_events.py`

`base.py` 定义 loader 协议、日期校验、重试和可选本地缓存。

### optimizers

`agent/backtest/optimizers/` 提供组合优化：

- 均值方差。
- 等波动。
- 风险平价。
- 最大分散化。

## `agent/src/factors/`

Alpha Zoo 实现。

- `base.py`：因子公式常用算子。
- `registry.py`：扫描因子、读取元数据、懒加载计算函数。
- `bench_runner.py`：批量评测、IC/IR 统计、分类。
- `zoo/`：具体因子实现。

当前包含：

- GTJA 191。
- Alpha101。
- Qlib 158。
- Academic 因子。

## `agent/src/swarm/`

多智能体研究团队。

| 文件/目录 | 说明 |
| --- | --- |
| `presets/` | YAML 预设，定义团队、任务 DAG、worker 角色 |
| `runtime.py` | 调度运行 DAG |
| `worker.py` | 单个 worker 执行逻辑 |
| `store.py` | run 状态、事件流、artifact 持久化 |
| `task_store.py` | task 状态文件和 DAG 算法 |
| `grounding.py` | 为 worker 注入行情和上下文 |
| `models.py` | SwarmRun、SwarmTask、SwarmEvent 等模型 |

Swarm 的状态存储结构：

```text
agent/.swarm/runs/{run_id}/
├── run.json
├── events.jsonl
├── tasks/
├── inboxes/
└── artifacts/
```

## `agent/src/session/`

Web/CLI 会话服务。

- `models.py`：Session、Message、Attempt。
- `store.py`：文件型 session store。
- `service.py`：session 生命周期和 Agent 调用。
- `events.py`：SSE 事件模型。
- `search.py`：SQLite FTS5 跨 session 搜索。

## `agent/src/memory/`

跨 session 记忆。

默认目录：

```text
~/.vibe-trading/memory/
├── MEMORY.md
└── *.md
```

每条记忆使用 Markdown + YAML frontmatter。

## `agent/src/live/` 和 `agent/src/trading/`

交易连接器和 live channel。

关键能力：

- 券商 profile 和 connector 配置。
- 账户、持仓、订单、行情、历史数据。
- mandate 约束。
- kill switch。
- 审计账本。
- OAuth token cache。

默认 live 状态目录：

```text
~/.vibe-trading/live/
```

## `agent/src/shadow_account/`

Shadow Account 交易行为复盘。

核心流程：

```text
交易流水 -> 行为画像 -> 规则提取 -> shadow 回测 -> 报告
```

主要模块：

- `extractor.py`：规则提取。
- `backtester.py`：shadow 回测。
- `reporter.py`：报告渲染。
- `storage.py`：profile/run/report 持久化。
- `codegen.py`：策略代码生成。

## `frontend/src/`

React Web UI。

| 目录 | 说明 |
| --- | --- |
| `pages/` | 页面：Home、Agent、RunDetail、AlphaZoo、Compare、Correlation、Runtime、Settings |
| `components/chat/` | 聊天时间线、消息气泡、工具进度、Swarm 状态卡 |
| `components/charts/` | 图表组件 |
| `components/layout/` | 页面布局、连接状态 |
| `stores/` | Zustand 状态 |
| `hooks/` | API/SSE/交互 hooks |
| `lib/` | API client、工具函数 |
| `types/` | TypeScript 类型 |

