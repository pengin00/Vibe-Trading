#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Vibe-Trading MCP 服务启动脚本
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 默认配置
MCP_PORT="${VIBE_MCP_PORT:-8900}"
MCP_TRANSPORT="${MCP_TRANSPORT:-stdio}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
  cat <<USAGE
用法: scripts/mcp.sh <命令>

命令:
  start              启动 MCP 服务（默认 stdio 模式）
  start-sse          启动 MCP 服务（SSE 模式）
  start-docker       在 Docker 容器中启动 MCP 服务
  stop               停止 MCP 服务（仅 SSE 模式）
  status             查看 MCP 服务状态
  config             显示 MCP 客户端配置
  test               测试 MCP 服务连接

传输模式:
  stdio              标准输入输出（默认，用于 Claude Desktop 等）
  sse                Server-Sent Events（用于 Web 客户端）

环境变量:
  VIBE_MCP_PORT      SSE 模式端口 (默认: 8900)
  MCP_TRANSPORT      传输模式 (stdio 或 sse)
  OLLAMA_BASE_URL    Ollama 地址 (默认: http://localhost:11434)

示例:
  # 启动 stdio 模式（用于 Claude Desktop）
  scripts/mcp.sh start

  # 启动 SSE 模式（用于 Web 集成）
  scripts/mcp.sh start-sse

  # 在 Docker 中启动
  scripts/mcp.sh start-docker

  # 获取配置用于客户端
  scripts/mcp.sh config
USAGE
}

find_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    echo "$PYTHON"
  elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    echo "$PROJECT_ROOT/.venv/bin/python"
  elif [[ -x "$PROJECT_ROOT/.venv/bin/python3" ]]; then
    echo "$PROJECT_ROOT/.venv/bin/python3"
  else
    echo "python3"
  fi
}

cmd_start_stdio() {
  info "启动 MCP 服务 (stdio 模式)..."
  info "按 Ctrl+C 停止"
  
  # 在 Docker 容器中运行
  docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec vibe-trading \
    python -m agent.mcp_server --transport stdio
}

cmd_start_sse() {
  info "启动 MCP 服务 (SSE 模式)..."
  info "SSE 端点: http://localhost:$MCP_PORT/sse"
  info "按 Ctrl+C 停止"
  
  # 在 Docker 容器中运行
  docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec vibe-trading \
    sh -c "python -m agent.mcp_server --transport sse --port $MCP_PORT"
}

cmd_start_docker() {
  info "在 Docker 容器中启动 MCP 服务..."
  local transport="${1:-sse}"
  local port="${2:-$MCP_PORT}"
  if [[ "$transport" == "stdio" ]]; then
    info "传输模式: stdio"
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec vibe-trading \
      python -m agent.mcp_server --transport stdio
  else
    info "传输模式: SSE"
    info "SSE 端点: http://localhost:$port/sse"
    docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -d vibe-trading \
      sh -c "python -m agent.mcp_server --transport sse --port $port"
    success "MCP SSE 服务已在 Docker 中启动"
    info "访问地址: http://localhost:$port/sse"
  fi
}

cmd_stop() {
  info "停止 MCP 服务..."
  pkill -f "agent.mcp_server" 2>/dev/null || true
  success "MCP 服务已停止"
}

cmd_status() {
  echo ""
  echo "=== MCP 服务状态 ==="
  if pgrep -f "agent.mcp_server" >/dev/null 2>&1; then
    success "MCP 服务: 运行中"
    ps aux | grep "agent.mcp_server" | grep -v grep | head -1
  else
    warn "MCP 服务: 未运行"
  fi
  echo ""
  echo "=== SSE 端点 ==="
  if curl -sf "http://localhost:$MCP_PORT/sse" >/dev/null 2>&1; then
    success "SSE 端点: 可访问"
  else
    warn "SSE 端点: 不可访问 (服务可能未运行)"
  fi
}

cmd_config() {
  echo ""
  echo "=== MCP 客户端配置 ==="
  echo ""
  echo "推荐使用 Docker 方式启动 MCP 服务："
  echo ""
  echo -e "${CYAN}--- 方式1: 使用脚本启动 ---${NC}"
  cat <<SCRIPT
# stdio 模式（Claude Desktop 等）
./scripts/mcp.sh start

# SSE 模式（Web 客户端）
./scripts/mcp.sh start-sse
SCRIPT

  echo ""
  echo -e "${CYAN}--- 方式2: 手动 Docker 命令 ---${NC}"
  cat <<DOCKER
# stdio 模式
docker compose exec vibe-trading python -m agent.mcp_server --transport stdio

# SSE 模式
docker compose exec vibe-trading sh -c 'python -m agent.mcp_server --transport sse --port 8900'
DOCKER

  echo ""
  echo -e "${CYAN}--- Claude Desktop 配置 (stdio) ---${NC}"
  cat <<CLAUDE_CONFIG
{
  "mcpServers": {
    "vibe-trading": {
      "command": "docker",
      "args": ["compose", "exec", "vibe-trading", "python", "-m", "agent.mcp_server"]
    }
  }
}
CLAUDE_CONFIG

  echo ""
  echo -e "${CYAN}--- OpenClaw 配置 ---${NC}"
  cat <<OPENCLAW
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
OPENCLAW

  echo ""
  echo -e "${CYAN}--- SSE 模式 (Web 客户端) ---${NC}"
  echo "SSE 端点: http://localhost:$MCP_PORT/sse"
  echo "SSE 端点: http://host.docker.internal:$MCP_PORT/sse (从 Docker 容器内)"
}

cmd_test() {
  echo ""
  echo "=== 测试 MCP 服务 ==="
  echo ""
  PYTHON_BIN="$(find_python)"
  echo -n "测试 stdio 连接: "
  if echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | \
     timeout 5 "$PYTHON_BIN" "$PROJECT_ROOT/agent/mcp_server.py" 2>/dev/null | \
     grep -q "result"; then
    success "成功"
  else
    warn "无法测试 stdio 连接（可能需要手动测试）"
  fi
  echo -n "测试 SSE 连接 (http://localhost:$MCP_PORT): "
  if curl -sf --max-time 2 "http://localhost:$MCP_PORT/sse" >/dev/null 2>&1; then
    success "成功"
  else
    warn "SSE 端点不可访问"
  fi
  echo ""
}

case "${1:-}" in
  start) cmd_start_stdio ;;
  start-sse) cmd_start_sse ;;
  start-docker)
    transport="${2:-sse}"
    port="${3:-$MCP_PORT}"
    cmd_start_docker "$transport" "$port"
    ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  config) cmd_config ;;
  test) cmd_test ;;
  -h|--help|help|"") usage ;;
  *)
    error "未知命令: $1"
    usage >&2
    exit 1
    ;;
esac
