# 投资工作台模块完整设计方案

本文设计一个面向个人投资管理的 Investment Workspace（投资工作台）模块。它的目标是把当前“提问式研究 Agent”升级为“有长期投资状态的个人投资管理平台”：系统知道用户关注哪些标的、持有哪些仓位、成本和决策依据是什么、哪些规则需要持续跟踪，并能把这些数据提供给 Agent、Swarm、定时任务和后续自动研报流程。

## 1. 目标与边界

### 1.1 核心目标

- 管理需要长期跟踪的投资标的，包括股票、ETF、基金、债券、加密货币、外汇、商品等。
- 管理当前持仓、分批买入/卖出成本、目标仓位、风险预算和盈亏。
- 记录每次研究、复盘、决策和执行计划，形成可追溯投资日志。
- 支持规则化跟踪：价格、涨跌幅、财报、新闻、估值、技术位、仓位风险等触发条件。
- 给 Agent 提供稳定的上下文，让它自动读取用户持仓和关注列表，而不是每次重新询问。
- 为后续自动化研究、定时研报、提醒、调仓建议和交易连接器联动打基础。

### 1.2 非目标

第一期不直接做自动下单，也不做券商资产同步的强依赖。交易连接器可以后续接入，但投资工作台本身先作为“研究、持仓、决策、跟踪”的主数据系统。

第一期也不追求完整机构级 PMS 功能，例如复杂税务批次、保证金风控、跨币种归因、组合优化器全自动执行等。这些可以在数据模型上预留扩展位。

## 2. 总体架构

```mermaid
flowchart TD
    UI["Web UI: 投资工作台"] --> API["FastAPI Portfolio APIs"]
    Agent["Agent / Chat"] --> Tools["Portfolio Tools"]
    Swarm["Swarm Research Teams"] --> Tools
    Scheduler["定时跟踪任务"] --> API
    Tools --> Service["Portfolio Service Layer"]
    API --> Service
    Service --> DB[("PostgreSQL")]
    Service --> Market["行情/新闻/财报数据源"]
    Market --> DB
```

### 2.1 模块分层

- **PostgreSQL**：投资工作台主数据库，存储标的、账户、持仓、规则、研报、决策日志、快照。
- **Portfolio Service Layer**：封装数据库读写、估值计算、仓位聚合、规则检测，避免业务代码散落 SQL。
- **FastAPI REST API**：提供给前端、自动化系统和外部调用。
- **Agent Tools**：让 Agent 可以读取和更新投资工作台数据。
- **Web UI**：提供标的池、持仓、标的详情、跟踪规则、决策日志等页面。
- **Scheduler / Automation**：后续用于定期刷新价格、检测触发规则、生成日报/周报。

## 3. PostgreSQL 选型

### 3.1 为什么直接使用 PostgreSQL

投资工作台是长期状态系统，后续会有多入口并发读写：

- Web UI 手动维护标的和持仓。
- Agent 运行中写入研究记录和决策日志。
- 定时任务刷新价格和触发规则。
- Swarm 多 Agent 同时写入研究报告。
- 未来券商连接器同步账户和成交。

SQLite 适合轻量本地缓存，但并发写入、复杂查询、JSONB、全文搜索、迁移部署都会逐渐吃力。PostgreSQL 更适合作为长期投资数据底座。

### 3.2 推荐依赖

后端建议使用：

```text
SQLAlchemy 2.x
Alembic
psycopg
```

当前项目 FastAPI 和多数工具链偏同步调用，第一期可以使用同步 SQLAlchemy + psycopg。未来如果 API 全面异步化，再评估 asyncpg。

### 3.3 Docker 存储

PostgreSQL 数据目录应绑定到本地持久化目录：

```text
/Users/pengying/workspace/ai-finance-os/vibe-data/postgres
```

推荐环境变量：

```env
DATABASE_URL=postgresql+psycopg://vibe:vibe_dev_password@127.0.0.1:5432/vibe_trading
```

Docker Compose 可增加：

```yaml
postgres:
  image: postgres:16
  environment:
    POSTGRES_DB: vibe_trading
    POSTGRES_USER: vibe
    POSTGRES_PASSWORD: vibe_dev_password
  ports:
    - "127.0.0.1:5432:5432"
  volumes:
    - /Users/pengying/workspace/ai-finance-os/vibe-data/postgres:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U vibe -d vibe_trading"]
    interval: 5s
    timeout: 3s
    retries: 20
```

`vibe-trading` 服务增加：

```yaml
depends_on:
  postgres:
    condition: service_healthy
environment:
  - DATABASE_URL=${DATABASE_URL:-postgresql+psycopg://vibe:vibe_dev_password@postgres:5432/vibe_trading}
```

## 4. 核心领域模型

### 4.1 Instrument 投资标的

投资标的是最核心的主数据。一个标的可以被加入观察池，也可以被持仓引用。

字段建议：

- `id`
- `symbol`：规范化代码，如 `GOOGL.US`、`0700.HK`、`BTC-USDT`
- `display_symbol`：前端展示代码，如 `GOOGL`
- `name`
- `asset_class`：equity、etf、fund、bond、crypto、fx、commodity、option
- `market`：US、HK、CN、CRYPTO、GLOBAL
- `currency`
- `exchange`
- `sector`
- `industry`
- `data_source_hint`
- `metadata`：JSONB，存储 ISIN、CUSIP、链上地址、基金公司等扩展字段
- `created_at`
- `updated_at`

唯一约束：

```text
unique(symbol, market)
```

### 4.2 Watchlist 关注标的池

Watchlist 管理“我为什么关注它、跟踪状态、投资假设”。

字段建议：

- `id`
- `instrument_id`
- `list_name`：默认 `default`，后续支持多列表
- `status`：watching、candidate、owned、paused、archived
- `priority`：1-5
- `tags`：text[]
- `thesis`：关注理由 / 投资假设
- `risk_notes`
- `target_price`
- `stop_price`
- `review_frequency`：daily、weekly、monthly、earnings_only
- `next_review_at`
- `created_at`
- `updated_at`

### 4.3 Portfolio Account 投资账户

用于区分券商账户、模拟账户、手工账户。

字段建议：

- `id`
- `name`
- `account_type`：manual、broker、paper、crypto_wallet
- `broker`
- `base_currency`
- `is_default`
- `metadata`：JSONB
- `created_at`
- `updated_at`

第一期可以默认创建一个 `Manual Portfolio`。

### 4.4 Position 持仓聚合

Position 表保存当前聚合持仓，便于快速查询和展示。

字段建议：

- `id`
- `account_id`
- `instrument_id`
- `quantity`
- `avg_cost`
- `cost_basis`
- `currency`
- `opened_at`
- `target_weight`
- `risk_budget`
- `stop_price`
- `take_profit_price`
- `status`：open、closed、watch_only
- `notes`
- `updated_at`

唯一约束：

```text
unique(account_id, instrument_id, status=open)
```

### 4.5 Position Lots 分批成本

用于记录分批买入/卖出、成本批次和未来税务/归因扩展。

字段建议：

- `id`
- `position_id`
- `side`：buy、sell、transfer_in、transfer_out、adjustment
- `trade_date`
- `quantity`
- `price`
- `fees`
- `currency`
- `source`：manual、broker_sync、agent
- `external_trade_id`
- `notes`
- `created_at`

第一期可从 lots 聚合生成 position，也可以手动维护 position 后补 lots。建议以 lots 为更可信数据，position 作为缓存聚合。

### 4.6 Price Snapshots 价格快照

用于记录定时获取的价格和分析时使用的价格证据。

字段建议：

- `id`
- `instrument_id`
- `source`
- `as_of`
- `price`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `currency`
- `interval`
- `raw`：JSONB
- `created_at`

索引：

```text
(instrument_id, as_of desc)
(source, as_of desc)
```

### 4.7 Research Reports 研究报告

记录 Agent 或 Swarm 生成的报告，并关联标的、持仓、session、run。

字段建议：

- `id`
- `instrument_id`
- `position_id`
- `report_type`：quick_analysis、deep_research、earnings_preview、risk_review、daily_update、weekly_review
- `title`
- `content`
- `summary`
- `rating`：bullish、neutral、bearish、hold、reduce、add
- `confidence`：0-100
- `data_sources`：JSONB
- `tool_trace_refs`：JSONB
- `session_id`
- `run_id`
- `swarm_run_id`
- `created_by`：user、agent、swarm、scheduler
- `created_at`

### 4.8 Tracking Rules 跟踪规则

规则用于自动提醒和自动研究触发。

字段建议：

- `id`
- `instrument_id`
- `position_id`
- `rule_type`：price、pnl、drawdown、news、earnings、valuation、technical、schedule
- `name`
- `enabled`
- `condition`：JSONB
- `action`：JSONB
- `severity`：info、warning、critical
- `cooldown_minutes`
- `last_triggered_at`
- `created_at`
- `updated_at`

示例：

```json
{
  "field": "price",
  "operator": "<=",
  "value": 315
}
```

```json
{
  "type": "run_analysis",
  "prompt_template": "分析 {symbol} 跌破止损价后的持仓处理建议"
}
```

### 4.9 Rule Trigger Events 规则触发记录

每次规则触发都要落日志，避免重复提醒和方便复盘。

字段建议：

- `id`
- `rule_id`
- `instrument_id`
- `position_id`
- `triggered_at`
- `observed_value`
- `message`
- `status`：new、acknowledged、dismissed、resolved
- `linked_report_id`
- `created_at`

### 4.10 Decision Logs 决策日志

记录最终人为或 Agent 辅助决策。

字段建议：

- `id`
- `instrument_id`
- `position_id`
- `decision_type`：buy、sell、add、reduce、hold、hedge、watch、stop_tracking
- `decision`
- `rationale`
- `price_at_decision`
- `quantity`
- `target_price`
- `stop_price`
- `confidence`
- `source_report_id`
- `session_id`
- `created_by`
- `created_at`

## 5. 推荐数据库表

第一期建表顺序：

```text
portfolio_accounts
instruments
watchlist_items
positions
position_lots
price_snapshots
research_reports
tracking_rules
rule_trigger_events
decision_logs
```

后续扩展表：

```text
portfolio_snapshots
portfolio_metrics
instrument_events
earnings_calendar
news_items
research_tasks
broker_sync_jobs
```

## 6. REST API 设计

### 6.1 Instruments

```text
GET    /portfolio/instruments
POST   /portfolio/instruments
GET    /portfolio/instruments/{instrument_id}
PATCH  /portfolio/instruments/{instrument_id}
DELETE /portfolio/instruments/{instrument_id}
```

筛选参数：

```text
asset_class
market
query
tag
status
```

### 6.2 Watchlist

```text
GET    /portfolio/watchlist
POST   /portfolio/watchlist
PATCH  /portfolio/watchlist/{item_id}
DELETE /portfolio/watchlist/{item_id}
```

常用操作：

```text
POST /portfolio/watchlist/{item_id}/pause
POST /portfolio/watchlist/{item_id}/archive
POST /portfolio/watchlist/{item_id}/promote-to-position
```

### 6.3 Accounts and Positions

```text
GET    /portfolio/accounts
POST   /portfolio/accounts
GET    /portfolio/positions
POST   /portfolio/positions
GET    /portfolio/positions/{position_id}
PATCH  /portfolio/positions/{position_id}
DELETE /portfolio/positions/{position_id}
```

Lots：

```text
GET    /portfolio/positions/{position_id}/lots
POST   /portfolio/positions/{position_id}/lots
PATCH  /portfolio/lots/{lot_id}
DELETE /portfolio/lots/{lot_id}
```

### 6.4 Research and Decisions

```text
GET  /portfolio/research
POST /portfolio/research
GET  /portfolio/instruments/{instrument_id}/research

GET  /portfolio/decisions
POST /portfolio/decisions
GET  /portfolio/instruments/{instrument_id}/decisions
```

### 6.5 Tracking Rules

```text
GET    /portfolio/rules
POST   /portfolio/rules
PATCH  /portfolio/rules/{rule_id}
DELETE /portfolio/rules/{rule_id}

GET    /portfolio/rule-events
POST   /portfolio/rules/{rule_id}/test
POST   /portfolio/rule-events/{event_id}/ack
```

### 6.6 Dashboard

```text
GET /portfolio/summary
GET /portfolio/dashboard
GET /portfolio/instruments/{instrument_id}/overview
```

`/portfolio/dashboard` 返回：

- 当前总市值
- 持仓数量
- 关注标的数量
- 今日触发规则
- 最近研究报告
- 最大仓位
- 最大浮亏/浮盈
- 待复盘标的

## 7. Agent 工具设计

### 7.1 查询工具

```text
list_tracked_instruments
get_instrument_profile
list_positions
get_position
get_watchlist
list_tracking_rules
list_recent_research
list_decision_logs
```

### 7.2 写入工具

```text
upsert_instrument
add_to_watchlist
upsert_position
add_position_lot
add_research_report
add_tracking_rule
record_decision
ack_rule_event
```

### 7.3 Agent 使用约束

- 分析用户持仓时，必须先调用 `get_position` 或 `list_positions`。
- 分析关注标的时，必须先调用 `get_instrument_profile` 和 `list_recent_research`。
- 给出买卖建议时，必须写入 `decision_logs`，除非用户明确表示只是闲聊。
- 生成研报时，必须写入 `research_reports`，并记录使用的数据源和工具 trace。
- 不允许凭记忆假设用户持仓、成本、仓位目标和止损价。

系统提示可增加：

```text
When the user asks about "my position", "my holdings", "我持仓", "我的成本", or "要不要加减仓", first read portfolio data through portfolio tools. Do not ask the user for data that already exists in the Investment Workspace.
```

## 8. Web UI 页面设计

### 8.1 投资工作台首页

首页展示：

- 总资产估算
- 持仓总数
- 观察标的数量
- 今日触发规则
- 待复盘标的
- 最近 Agent 研究结论
- 最大风险持仓

### 8.2 标的池页面

表格列：

- 标的
- 名称
- 市场
- 资产类型
- 状态
- 标签
- 优先级
- 最新价
- 最近研究结论
- 下次复盘时间

操作：

- 新增标的
- 批量导入
- 加入/移出关注
- 转为持仓
- 触发 Agent 分析

### 8.3 持仓页面

表格列：

- 标的
- 数量
- 成本价
- 当前价
- 市值
- 浮盈亏
- 仓位占比
- 目标仓位
- 止损价
- 最后分析时间

操作：

- 新增持仓
- 录入买卖批次
- 更新成本
- 生成持仓分析
- 记录决策

### 8.4 标的详情页

建议布局：

- 顶部：标的信息、当前价、涨跌幅、持仓状态
- 左侧：价格图、关键指标、规则触发
- 右侧：当前持仓、成本、目标价、止损、风险备注
- 下方 Tabs：
  - 研究报告
  - 决策日志
  - 交易批次
  - 跟踪规则
  - 数据快照
  - Agent Trace

### 8.5 跟踪规则页面

展示所有规则：

- 规则名
- 标的
- 条件
- 动作
- 严重级别
- 是否启用
- 最近触发

## 9. 自动化跟踪流程

### 9.1 每日跟踪

```text
定时任务启动
-> 读取启用的 watchlist 和 positions
-> 拉取最新价格/新闻/财报日期
-> 写入 price_snapshots
-> 执行 tracking_rules
-> 生成 rule_trigger_events
-> 对 critical 事件触发 Agent 快速分析
-> 生成 daily_update research_report
```

### 9.2 自动研报

自动研报可以分三档：

- **Quick Update**：价格、盈亏、规则触发、新闻摘要。
- **Position Review**：结合成本、仓位、止损、技术面和基本面。
- **Deep Research**：调用 Swarm，多 Agent 分析基本面、技术面、风险和操作建议。

### 9.3 决策闭环

```text
规则触发 / 用户提问
-> Agent 读取投资工作台上下文
-> 拉取最新数据
-> 生成分析报告
-> 写 research_reports
-> 如有明确建议，写 decision_logs
-> 用户确认后，可联动交易连接器
```

## 10. 数据安全和隐私

- API 默认仍应保持本地/鉴权访问。
- PostgreSQL 不应暴露到公网，Docker 端口绑定 `127.0.0.1`。
- 账户、券商、API key 不进入普通研究报告正文。
- Agent trace 展示时继续复用当前 redaction 机制。
- 决策日志和交易批次属于高敏感数据，后续多用户时需要用户隔离。

## 11. 迁移与版本管理

使用 Alembic 管理 schema：

```text
agent/src/portfolio/models.py
agent/src/portfolio/db.py
agent/src/portfolio/service.py
agent/src/portfolio/schemas.py
agent/src/portfolio/api.py
agent/src/portfolio/tools.py
alembic/
```

迁移策略：

- 每次表结构变化生成 Alembic revision。
- Docker 启动时可选择自动执行迁移，或提供 `vibe-trading db upgrade` 命令。
- `DATABASE_URL` 未配置时，Portfolio API 返回明确错误，不影响现有 Agent 基础功能。

## 12. 第一阶段实施计划

### Phase 1: 数据库与基础 API

- 引入 SQLAlchemy、psycopg、Alembic。
- Docker Compose 增加 PostgreSQL。
- 创建核心表：
  - accounts
  - instruments
  - watchlist_items
  - positions
  - position_lots
  - research_reports
  - decision_logs
  - tracking_rules
- 实现 `/portfolio/*` 基础 CRUD。

### Phase 2: 前端投资工作台

- 新增导航入口：投资工作台。
- 页面：
  - 标的池
  - 持仓
  - 标的详情
- 支持手工新增标的、持仓、批次、规则。

### Phase 3: Agent 工具接入

- 增加 portfolio tools。
- 修改系统提示：
  - 涉及“我的持仓/成本/关注标的”必须先读取投资工作台。
  - 研报和建议写回 research_reports / decision_logs。
- 在工具记录面板中展示 portfolio 工具调用。

### Phase 4: 自动跟踪

- 定时刷新 watchlist/positions 价格。
- 执行 tracking rules。
- 生成 rule_trigger_events。
- 支持一键“基于触发事件生成分析”。

### Phase 5: 自动研报和交易连接器联动

- 每日/每周自动生成持仓简报。
- 对 critical 规则触发自动调用 Agent/Swarm。
- 未来可在用户确认后联动交易连接器，但默认只研究不交易。

## 13. 推荐第一版最小可用范围

第一版不要做太大，建议交付：

- PostgreSQL 接入和迁移框架。
- 标的表、关注表、账户表、持仓表、批次表。
- 标的池页面。
- 持仓页面。
- `get_position`、`list_positions`、`add_research_report`、`record_decision` 四个 Agent 工具。
- Agent 在分析“我的持仓”时自动读取持仓数据。

这样可以最快形成闭环：

```text
录入持仓 -> 用户提问 -> Agent 自动读取持仓 -> 调工具取最新数据 -> 生成建议 -> 写回研究记录/决策日志
```

完成这个闭环后，再扩展自动跟踪和自动研报会更稳。

