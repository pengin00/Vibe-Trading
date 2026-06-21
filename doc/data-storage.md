# 运行数据与持久化

Vibe-Trading 使用文件系统和轻量数据库保存运行数据，没有强依赖 PostgreSQL/MySQL。

## 存储总览

| 数据 | 容器内路径 | 默认宿主路径/说明 |
| --- | --- | --- |
| Agent run | `/app/agent/runs` | `agent/runs`，Docker 已挂到 `vibe-data/runs` |
| Session | `/app/agent/sessions` | `agent/sessions`，Docker 已挂到 `vibe-data/sessions` |
| 上传文件 | `/app/agent/uploads` | `agent/uploads`，Docker 已挂到 `vibe-data/uploads` |
| Swarm run | `/app/agent/.swarm/runs` | Docker 已挂到 `vibe-data/swarm-runs` |
| 用户级状态 | `/home/vibe/.vibe-trading` | Docker 已挂到 `vibe-data/home` |

当前 Docker bind mount 根目录：

```text
/Users/pengying/workspace/ai-finance-os/vibe-data
```

## Run 存储

路径：

```text
agent/runs/{run_id}/
```

典型结构：

```text
{run_id}/
├── req.json
├── state.json
├── code/
├── logs/
└── artifacts/
```

用途：

- 保存用户请求。
- 保存执行状态。
- 保存生成代码。
- 保存回测指标、图表、报告、run card 等 artifacts。

## Session 存储

路径：

```text
agent/sessions/{session_id}/
```

典型结构：

```text
{session_id}/
├── session.json
├── messages.jsonl
└── attempts/
    └── {attempt_id}/
        └── attempt.json
```

`messages.jsonl` 是 append-only 消息日志。

## Session 搜索和 Research Goal

路径：

```text
~/.vibe-trading/sessions.db
```

实现：

- SQLite。
- FTS5 全文索引。
- WAL 模式。

用途：

- 跨 session 搜索历史对话。
- 保存 Research Goal 相关结构化状态。

## Persistent Memory

路径：

```text
~/.vibe-trading/memory/
```

结构：

```text
memory/
├── MEMORY.md
└── *.md
```

说明：

- `MEMORY.md` 是记忆索引。
- 单条记忆是 Markdown 文件，带 YAML frontmatter。
- Agent 在新 session 开始时读取 memory snapshot。

## Swarm 存储

路径：

```text
agent/.swarm/runs/{run_id}/
```

结构：

```text
{run_id}/
├── run.json
├── events.jsonl
├── tasks/
├── inboxes/
└── artifacts/
```

说明：

- `run.json` 保存 SwarmRun 总状态。
- `events.jsonl` 是 SSE/恢复使用的事件日志。
- `tasks/` 保存每个 worker task 状态。
- `artifacts/` 保存 worker 输出。

## Shadow Account

默认路径：

```text
~/.vibe-trading/
├── shadow_accounts/
├── shadow_runs/
└── shadow_reports/
```

用途：

- `shadow_accounts/` 保存提取出的交易规则画像。
- `shadow_runs/` 保存 shadow 回测结果。
- `shadow_reports/` 保存 HTML/PDF 报告。

## Live Trading 状态

默认路径：

```text
~/.vibe-trading/live/
```

典型结构：

```text
live/
├── HALT
├── audit.jsonl
└── {broker}/
    ├── oauth/
    ├── mandate.json
    ├── trade_counter.json
    └── proposals/
```

说明：

- `HALT` 是全局 kill switch。
- `audit.jsonl` 是追加式审计账本。
- `mandate.json` 是用户授权的交易约束。
- OAuth token cache 在 broker 子目录下。

## 行情和 Alpha 缓存

默认路径：

```text
~/.vibe-trading/cache/
```

类型：

- loader 缓存：`~/.vibe-trading/cache/loaders/.../*.parquet`
- Alpha universe 缓存：`~/.vibe-trading/cache/*.pkl`

loader 缓存默认关闭，可通过：

```text
VIBE_TRADING_DATA_CACHE=1
```

开启。

## Docker 数据保护

当前项目已把容器数据绑定到本地：

```text
/Users/pengying/workspace/ai-finance-os/vibe-data
```

因此：

- `docker compose up --build` 不会清空数据。
- `docker compose down` 不会清空数据。
- `docker compose down -v` 会删除 Docker named volumes，但不会删除 bind mount 目录中的数据。

建议定期备份：

```bash
tar -czf vibe-data-backup.tgz /Users/pengying/workspace/ai-finance-os/vibe-data
```

