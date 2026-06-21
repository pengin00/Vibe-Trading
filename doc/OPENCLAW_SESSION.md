# OpenClaw 会话管理指南

## 核心概念

### Vibe-Trading 的会话机制

Vibe-Trading 使用 **session_id** 来区分不同的对话会话：

- **每个 session_id 是独立的**：不同 session_id 之间不会共享上下文
- **同一 session_id 会共享历史**：相同 session_id 的多次调用会累积对话历史
- **session_id 由客户端传递**：MCP 工具要求客户端提供 `session_id` 参数

### OpenClaw 如何处理会话

OpenClaw 作为 MCP 客户端，**需要自己管理 session_id**。关键问题：

**❌ 默认行为：可能共用同一个 session_id**

如果 OpenClaw 在多次调用时传递相同的 `session_id`，所有对话会累积到同一个会话中，导致：
- 上下文混乱
- 目标冲突
- 回测结果混淆

**✅ 正确做法：每次新对话创建新的 session_id**

## 解决方案

### 方案1: OpenClaw 自动生成 session_id（推荐）

在 OpenClaw 配置或技能调用时，让 OpenClaw 为每次对话生成唯一的 session_id：

```yaml
# ~/.openclaw/config.yaml
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
    
    # 如果 OpenClaw 支持变量替换
    variables:
      session_id: "{{uuid}}"  # 或其他唯一标识符生成方式
```

### 方案2: 手动指定 session_id

在每次调用 MCP 工具时，显式传入唯一的 session_id：

```javascript
// 示例：在 OpenClaw 技能脚本中
const sessionId = generateUniqueId(); // 使用时间戳、UUID 等

await callTool('start_research_goal', {
  session_id: sessionId,
  objective: "分析 AAPL 股票",
  criteria: ["基本面分析", "技术面分析"]
});
```

### 方案3: 基于对话线程管理 session_id

为每个对话线程维护一个固定的 session_id：

```python
# 伪代码示例
class ConversationThread:
    def __init__(self):
        self.session_id = generate_uuid()
    
    def ask(self, question):
        return call_mcp_tool(
            session_id=self.session_id,  # 同一线程使用相同 ID
            question=question
        )
```

## 创建新会话的方法

### 方法1: 生成新的 UUID

```bash
# Linux/macOS
NEW_SESSION_ID=$(uuidgen)

# Python
import uuid
session_id = uuid.uuid4().hex[:12]

# JavaScript
const sessionId = crypto.randomUUID().slice(0, 12);
```

### 方法2: 使用时间戳 + 随机数

```python
import time
import random
session_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
```

### 方法3: 使用对话标题哈希

```python
import hashlib
title = "分析 AAPL 股票"
session_id = hashlib.md5(title.encode()).hexdigest()[:12]
```

## 最佳实践

### ✅ 推荐做法

1. **每次新话题创建新会话**
   ```
   用户: "分析 AAPL" → session_id: abc123
   用户: "分析 TSLA" → session_id: def456  # 新的 session_id
   ```

2. **同一话题延续使用相同会话**
   ```
   用户: "分析 AAPL" → session_id: abc123
   用户: "它的基本面如何？" → session_id: abc123  # 继续同一会话
   ```

3. **在 OpenClaw 中按线程隔离**
   ```yaml
   threads:
     aapl-analysis:
       session_id: "aapl_20240621"
     tsla-analysis:
       session_id: "tsla_20240621"
   ```

### ❌ 避免的做法

1. **硬编码固定 session_id**
   ```yaml
   # 错误！所有对话都会混在一起
   session_id: "default"
   ```

2. **不传递 session_id**
   ```python
   # 错误！可能导致工具调用失败或使用默认值
   start_research_goal(objective="...")  # 缺少 session_id
   ```

## OpenClaw 配置示例

### 基础配置

```yaml
# ~/.openclaw/config.yaml
skills:
  - name: vibe-trading
    command: docker
    args:
      - compose
      - -f
      - /Users/pengying/workspace/ai-finance-os/Vibe-Trading/docker-compose.yml
      - exec
      - vibe-trading
      - python
      - -m
      - agent.mcp_server
```

### 高级配置（支持会话隔离）

```yaml
# ~/.openclaw/config.yaml
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
    
    # 如果 OpenClaw 支持会话变量
    context:
      session_strategy: "per_thread"  # 每个线程独立会话
      session_prefix: "vibe"          # session_id 前缀
```

## 调试技巧

### 查看当前会话列表

```bash
# 通过 API 查看所有会话
curl http://localhost:8899/sessions | jq

# 或通过 Docker
docker compose exec vibe-trading python -c "
from src.session.store import SessionStore
store = SessionStore()
for s in store.list_sessions():
    print(f'{s.session_id}: {s.title}')
"
```

### 检查特定会话的历史

```bash
# 查看会话详情
curl http://localhost:8899/sessions/{session_id} | jq

# 查看会话消息
curl http://localhost:8899/sessions/{session_id}/messages | jq
```

### 清理旧会话

```bash
# 删除特定会话
curl -X DELETE http://localhost:8899/sessions/{session_id}

# 或通过文件系统
rm -rf /path/to/vibe-data/sessions/{session_id}
```

## 常见问题

### Q1: OpenClaw 会自动管理 session_id 吗？

**答：** 取决于 OpenClaw 的版本和配置。较新版本可能支持自动会话管理，但建议：
- 查阅 OpenClaw 文档确认
- 或在调用工具时显式传递 session_id

### Q2: 如何确保不同用户的会话隔离？

**答：** 
- 为每个用户生成独立的 session_id 前缀
- 例如：`user1_abc123`, `user2_def456`

### Q3: session_id 有长度限制吗？

**答：** 
- Vibe-Trading 使用 12 字符的十六进制字符串（来自 UUID）
- 建议使用类似格式：`uuid4().hex[:12]`

### Q4: 会话会过期吗？

**答：** 
- 会话永久保存，除非手动删除
- 可以通过 `list_sessions` 查看并清理旧会话

## 总结

| 场景 | session_id 策略 |
|------|----------------|
| 新话题 | 生成新的 session_id |
| 延续对话 | 使用相同的 session_id |
| 多用户 | 每个用户独立的 session_id 空间 |
| 测试 | 使用时间戳或 UUID |

**关键原则：** 
- **一个 session_id = 一个独立的对话上下文**
- **不要在不同话题间共用 session_id**
- **在 OpenClaw 中按线程或对话隔离 session_id**
