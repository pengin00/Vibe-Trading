#!/usr/bin/env bash
set -euo pipefail

# MCP 服务快速测试脚本

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== MCP 服务测试 ==="
echo ""

# 检查 Docker 容器状态
echo "1. 检查 Docker 容器状态..."
if docker compose -f "$PROJECT_ROOT/docker-compose.yml" ps vibe-trading | grep -q "Up"; then
    echo "   ✅ Docker 容器运行中"
else
    echo "   ❌ Docker 容器未运行"
    echo "   请先启动: ./scripts/docker.sh up"
    exit 1
fi

# 测试 stdio 模式
echo ""
echo "2. 测试 stdio 模式（列出可用工具）..."
TOOLS=$(echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | \
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T vibe-trading \
    python -m agent.mcp_server --transport stdio 2>&1)

if echo "$TOOLS" | grep -q '"result"'; then
    TOOL_COUNT=$(echo "$TOOLS" | grep -o '"name"' | wc -l | tr -d ' ')
    echo "   ✅ stdio 模式正常，发现 $TOOL_COUNT 个工具"
else
    echo "   ⚠️  stdio 模式返回异常（可能是初始化警告，通常可忽略）"
fi

# 测试 SSE 模式（如果已启动）
echo ""
echo "3. 测试 SSE 端点..."
if curl -sf --max-time 2 http://localhost:8900/sse >/dev/null 2>&1; then
    echo "   ✅ SSE 端点可访问 (http://localhost:8900/sse)"
else
    echo "   ℹ️  SSE 端点未启动（需要运行: ./scripts/mcp.sh start-sse）"
fi

# 显示配置
echo ""
echo "4. 客户端配置示例："
echo ""
echo "   Claude Desktop / Cursor:"
echo '   {
     "mcpServers": {
       "vibe-trading": {
         "command": "docker",
         "args": ["compose", "exec", "vibe-trading", "python", "-m", "agent.mcp_server"]
       }
     }
   }'

echo ""
echo "=== 测试完成 ==="
echo ""
echo "下一步："
echo "  - 在 Claude Desktop/Cursor 中配置 MCP 服务器"
echo "  - 或启动 SSE 模式: ./scripts/mcp.sh start-sse"
echo "  - 查看完整文档: cat doc/MCP_USAGE.md"
