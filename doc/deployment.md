# 部署与启动

## Docker 启动

项目根目录执行：

```bash
cp agent/.env.example agent/.env
# 编辑 agent/.env，设置 LLM provider 和 key
docker compose up --build
```

后台启动：

```bash
docker compose up -d --build
```

访问：

```text
http://localhost:8899
```

## 本项目当前本地数据挂载

当前已经创建了 `docker-compose.override.yml`，把容器数据挂载到：

```text
/Users/pengying/workspace/ai-finance-os/vibe-data
```

映射关系：

```text
/Users/pengying/workspace/ai-finance-os/vibe-data/runs
  -> /app/agent/runs

/Users/pengying/workspace/ai-finance-os/vibe-data/sessions
  -> /app/agent/sessions

/Users/pengying/workspace/ai-finance-os/vibe-data/home
  -> /home/vibe/.vibe-trading

/Users/pengying/workspace/ai-finance-os/vibe-data/swarm-runs
  -> /app/agent/.swarm/runs

/Users/pengying/workspace/ai-finance-os/vibe-data/uploads
  -> /app/agent/uploads
```

这样即使执行 `docker compose down -v`，上述 bind mount 目录中的数据也不会被 Docker volume 删除。

## Docker 内执行 CLI

服务已启动时执行同步长任务：

```bash
docker compose exec vibe-trading \
  vibe-trading run -p "帮我回测 BTC-USDT 2024 年 20/50 均线策略"
```

进入容器：

```bash
docker compose exec vibe-trading sh
```

一次性运行：

```bash
docker compose run --rm vibe-trading \
  vibe-trading run -p "分析 NVDA 最近的基本面、技术面和风险"
```

查看历史：

```bash
docker compose exec vibe-trading vibe-trading --list
docker compose exec vibe-trading vibe-trading --show <run_id>
```

## Swarm CLI

```bash
docker compose exec vibe-trading \
  vibe-trading --swarm-run investment_committee '{"topic":"分析 NVDA 是否适合中长期持有"}'
```

长任务可通过环境变量调超时：

```bash
docker compose exec \
  -e SWARM_TIMEOUT=3600 \
  -e VIBE_TRADING_TOOL_TIMEOUT_SECONDS=3600 \
  vibe-trading \
  vibe-trading run -p "跑一个长周期回测并生成报告"
```

## 本地开发启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp agent/.env.example agent/.env
vibe-trading serve --port 8899
```

前后端分开：

```bash
# Terminal 1
vibe-trading serve --port 8899

# Terminal 2
cd frontend
npm install
npm run dev
```

前端开发地址：

```text
http://localhost:5899
```

## LLM 配置

配置文件：

```text
agent/.env
```

当前常用字段：

```text
LANGCHAIN_PROVIDER=deepseek
LANGCHAIN_MODEL_NAME=deepseek-v4-flash
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

`agent/.env` 是本地敏感配置，不应提交到 Git。

## 远程访问和认证

本机 `localhost` 开发访问通常无需认证。若从局域网、其他机器或公网访问，建议设置：

```text
API_AUTH_KEY=<strong-secret>
```

请求时携带：

```bash
-H "Authorization: Bearer <API_AUTH_KEY>"
```

不要在未设置 `API_AUTH_KEY` 的情况下把 `8899` 暴露到公网。

