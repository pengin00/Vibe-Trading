# MCP 服务使用指南

## 概述

Vibe-Trading MCP (Model Context Protocol) 服务提供金融研究工具给任何 MCP 客户端（Claude Desktop、Cursor、OpenClaw 等）。

## 快速开始

### 方式1: 使用脚本（推荐）

```bash
# stdio 模式 - 用于 Claude Desktop、Cursor 等桌面客户端
./scripts/mcp.sh start

# SSE 模式 - 用于 Web 集成
./scripts/mcp.sh start-sse

# 查看配置
./scripts/mcp.sh config

# 测试连接
./scripts/mcp.sh test
```

### 方式2: 手动 Docker 命令

```bash
# stdio 模式
docker compose exec vibe-trading python -m agent.mcp_server --transport stdio

# SSE 模式
docker compose exec vibe-trading sh -c 'python -m agent.mcp_server --transport sse --port 8900'
```

## 客户端配置

### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "vibe-trading": {
      "command": "docker",
      "args": ["compose", "exec", "vibe-trading", "python", "-m", "agent.mcp_server"]
    }
  }
}
```

**注意：** 需要确保在 Vibe-Trading 项目目录下运行 Docker Compose。

### OpenClaw

编辑 `~/.openclaw/config.yaml`：

```yaml
skills:
  - name: vibe-trading
    command: docker
    args:
      - compose
      - exec
      - vibe-trading
      - python
      - -m
      - agent.mcp_server
```

### Cursor

在 Cursor 设置中添加 MCP 服务器：

```json
{
  "mcpServers": {
    "vibe-trading": {
      "command": "docker",
      "args": ["compose", "exec", "vibe-trading", "python", "-m", "agent.mcp_server"]
    }
  }
}
```

### SSE 模式（Web 客户端）

对于支持 SSE 的 Web 客户端：

- **本地端点**: `http://localhost:8900/sse`
- **Docker 内端点**: `http://host.docker.internal:8900/sse`

## 可用工具

MCP 服务提供以下工具类别：

### 技能管理
- `list_skills` - 列出所有可用技能
- `load_skill` - 加载指定技能的完整文档

### 研究目标
- `ensure_ui_session` - 为外部 MCP 会话创建/复用 Vibe-Trading UI 会话
- `append_ui_session_message` - 将 MCP 客户端消息镜像到 Vibe-Trading Sessions UI
- `start_research_goal` - 创建研究目标
- `get_research_goal` - 获取当前研究目标
- `add_goal_evidence` - 添加证据
- `update_research_goal_status` - 更新目标状态

### 回测
- `backtest` - 运行向量化回测

### 因子分析
- `factor_analysis` - 计算因子 IC/IR 分析

### 期权定价
- `analyze_options` - Black-Scholes 期权定价和 Greeks

### 市场数据
- `get_market_data` - 获取 OHLCV 市场数据

### 文件操作
- `read_file` - 读取文件
- `write_file` - 写入文件

### Web 工具
- `read_url` - 读取网页内容
- `web_search` - DuckDuckGo 搜索
- `read_document` - 读取 PDF 文档

### 交易连接器
- `trading_connections` - 列出交易连接器
- `trading_select_connection` - 选择连接器
- `trading_check` - 检查连接状态
- `trading_account` - 获取账户信息
- `trading_positions` - 获取持仓
- `trading_orders` - 获取订单
- `trading_quote` - 获取报价
- `trading_history` - 获取历史数据

### Swarm 多智能体
- `list_swarm_presets` - 列出预设团队
- `run_swarm` - 运行多智能体团队
- `get_swarm_status` - 获取运行状态
- `get_run_result` - 获取最终报告
- `list_runs` - 列出运行记录
- `reap_stale_runs` - 清理过期运行
- `retry_run` - 重试失败的运行

### Shadow Account
- `extract_shadow_strategy` - 提取影子策略
- `run_shadow_backtest` - 运行影子回测
- `render_shadow_report` - 生成影子报告
- `scan_shadow_signals` - 扫描信号

### 交易日志
- `analyze_trade_journal` - 分析交易日志

## 故障排除

### 问题1: ModuleNotFoundError: No module named 'fastmcp'

**原因：** 在宿主机上直接运行，缺少依赖

**解决：** 使用 Docker 容器运行（已修复）

```bash
# 错误方式（不推荐）
python -m agent.mcp_server

# 正确方式（推荐）
docker compose exec vibe-trading python -m agent.mcp_server
```

### 问题2: Docker compose 找不到服务

**原因：** 未在项目目录运行

**解决：** 切换到项目目录

```bash
cd /Users/pengying/workspace/ai-finance-os/Vibe-Trading
docker compose exec vibe-trading python -m agent.mcp_server
```

### 问题3: Claude Desktop 无法连接

**原因：** Claude Desktop 配置中的命令路径不对

**解决：** 使用绝对路径或确保在工作目录

```json
{
  "mcpServers": {
    "vibe-trading": {
      "command": "/usr/local/bin/docker",
      "args": [
        "compose",
        "-f",
        "/Users/pengying/workspace/ai-finance-os/Vibe-Trading/docker-compose.yml",
        "exec",
        "vibe-trading",
        "python",
        "-m",
        "agent.mcp_server"
      ]
    }
  }
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VIBE_MCP_PORT` | 8900 | SSE 模式端口 |
| `OLLAMA_BASE_URL` | http://localhost:11434 | Ollama 服务地址 |

## 更多信息

- MCP 服务器代码: [`agent/mcp_server.py`](../agent/mcp_server.py)
- API 文档: [http://localhost:8899/docs](http://localhost:8899/docs)
- FastMCP 文档: https://gofastmcp.com
