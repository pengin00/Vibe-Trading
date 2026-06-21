# Docker 数据持久化配置

## 问题

使用 `docker-compose.yml` 时，会话数据存储在使用 Docker 命名卷中，重启容器后本地目录看不到历史会话。

## 解决方案

### 1. docker-compose.override.yml

Docker Compose 会自动合并 `docker-compose.override.yml`，将命名卷覆盖为本地路径映射：

```yaml
services:
  vibe-trading:
    volumes:
      - /Users/pengying/workspace/ai-finance-os/vibe-data/runs:/app/agent/runs
      - /Users/pengying/workspace/ai-finance-os/vibe-data/sessions:/app/agent/sessions
      - /Users/pengying/workspace/ai-finance-os/vibe-data/home:/home/vibe/.vibe-trading
      - /Users/pengying/workspace/ai-finance-os/vibe-data/swarm-runs:/app/agent/.swarm/runs
      - /Users/pengying/workspace/ai-finance-os/vibe-data/uploads:/app/agent/uploads
```

### 2. 应用更改

```bash
# 停止并删除旧容器（包括命名卷）
docker compose down

# 重新创建容器（使用 override 配置）
docker compose up -d vibe-trading

# 验证挂载
docker exec vibe-trading ls -la /app/agent/sessions/

# 验证 API
curl http://localhost:8899/sessions | jq '.'
```

### 3. 数据位置

所有数据存储在本地目录 `/Users/pengying/workspace/ai-finance-os/vibe-data/`：

- `sessions/` - 会话记录
- `runs/` - 策略运行记录
- `home/` - 用户配置和记忆
- `uploads/` - 上传文件
- `swarm-runs/` - Swarm 运行记录

### 4. 注意事项

- **首次启动**：需要执行 `docker compose down` 清理旧的命名卷
- **备份**：直接备份 `/Users/pengying/workspace/ai-finance-os/vibe-data/` 即可
- **迁移**：复制整个 `vibe-data` 目录到新机器即可迁移数据
