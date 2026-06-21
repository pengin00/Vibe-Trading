# REST API 与长任务结果获取

服务地址默认：

```text
http://localhost:8899
```

交互文档：

```text
http://localhost:8899/docs
```

## API 分类

| 类型 | 典型接口 | 说明 |
| --- | --- | --- |
| Session | `/sessions` | 普通 Web/Agent 对话 |
| Run | `/runs` | 查询回测和 Agent run 产物 |
| Upload | `/upload` | 上传文件供 Agent 使用 |
| Swarm | `/swarm/runs` | 多智能体长任务 |
| Alpha | `/alpha/*` | Alpha Zoo 浏览、bench、compare |
| Settings | `/settings/*` | Web UI 本地配置 |

## 普通 Agent 会话

### 创建 session

```bash
curl -X POST http://localhost:8899/sessions
```

返回中包含 `session_id`。

### 发送任务

```bash
curl -X POST http://localhost:8899/sessions/<session_id>/messages \
  -H "Content-Type: application/json" \
  -d '{"content":"帮我回测 BTC-USDT 2024 年 20/50 均线策略，输出收益率和最大回撤"}'
```

### 订阅事件流

```bash
curl http://localhost:8899/sessions/<session_id>/events
```

该接口是 SSE，用于获取：

- assistant 消息增量。
- 工具调用进度。
- run_id。
- 错误。
- 完成事件。

### 查询 run 结果

```bash
curl http://localhost:8899/runs/<run_id>
```

返回 run 的指标、artifacts、图表 payload、报告、代码等。

## Run 查询

### 列出 run

```bash
curl http://localhost:8899/runs
```

### 查询详情

```bash
curl http://localhost:8899/runs/<run_id>
```

### Pine/多平台导出

```bash
curl http://localhost:8899/runs/<run_id>/pine
```

## Swarm 长任务

### 启动 Swarm

```bash
curl -X POST http://localhost:8899/swarm/runs \
  -H "Content-Type: application/json" \
  -d '{
    "preset_name": "investment_committee",
    "variables": {
      "topic": "分析 NVDA 是否适合中长期持有"
    }
  }'
```

返回 `run_id`。

### 订阅 Swarm 事件

```bash
curl http://localhost:8899/swarm/runs/<run_id>/events
```

事件中可看到每个 worker 状态：

```text
pending / running / done / failed / blocked / retrying
```

Swarm 状态和产物保存在：

```text
agent/.swarm/runs/<run_id>/
```

Docker 当前映射到：

```text
/Users/pengying/workspace/ai-finance-os/vibe-data/swarm-runs/<run_id>/
```

## Alpha Bench 长任务

### 启动 bench

```bash
curl -X POST http://localhost:8899/alpha/bench \
  -H "Content-Type: application/json" \
  -d '{
    "zoo": "gtja191",
    "universe": "csi300",
    "period": "2018-2025",
    "top": 20
  }'
```

返回 `job_id`。

### 订阅进度

```bash
curl http://localhost:8899/alpha/bench/<job_id>/stream
```

## 长任务获取结果模式

长任务不要只等待创建接口的 HTTP 响应。推荐模式：

```text
POST 创建任务
  -> 返回 session_id/run_id/job_id
  -> GET events/stream 订阅 SSE 进度
  -> 完成后 GET /runs/{run_id} 或读取对应 artifact
```

## 认证

本地 loopback 访问通常不需要认证。如果设置了 `API_AUTH_KEY` 或从非本机访问，带上：

```bash
curl http://localhost:8899/runs \
  -H "Authorization: Bearer <API_AUTH_KEY>"
```

浏览器 SSE 鉴权由 Web UI Settings 保存 API key 后处理。

