#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Vibe-Trading Docker 启动脚本
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"

# 默认配置
BACKEND_PORT="${VIBE_BACKEND_PORT:-8899}"
FRONTEND_PORT="${VIBE_FRONTEND_PORT:-5899}"
MCP_PORT="${VIBE_MCP_PORT:-8900}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://host.docker.internal:11434}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
  cat <<USAGE
用法: scripts/docker.sh <命令>

命令:
  up                 构建并启动服务（后端+前端，单端口）
  down               停止所有服务
  restart           重启服务
  build              仅构建镜像（不启动）
  logs               查看日志
  status             查看服务状态
  shell              进入容器 shell
  health             健康检查
  dev                启动开发模式（前后端分离，热重载）
  clean              清理 Docker 资源
  urls               显示访问地址

环境变量:
  VIBE_BACKEND_PORT   后端端口 (默认: 8899)
  VIBE_FRONTEND_PORT  前端端口 (默认: 5899)
  VIBE_MCP_PORT       MCP SSE 端口 (默认: 8900)
  OLLAMA_BASE_URL     Ollama 服务地址 (默认: http://host.docker.internal:11434)

示例:
  # 启动所有服务
  scripts/docker.sh up

  # 仅启动后端
  scripts/docker.sh up-backend

  # 查看后端日志
  scripts/docker.sh logs backend

  # 进入容器
  scripts/docker.sh shell
USAGE
}

check_docker() {
  if ! command -v docker &>/dev/null; then
    error "Docker 未安装，请先安装 Docker"
    exit 1
  fi
  if ! docker info &>/dev/null; then
    error "Docker 未运行，请先启动 Docker Desktop"
    exit 1
  fi
}

wait_healthy() {
  local service="$1"
  local port="$2"
  local name="$3"
  local max_attempts=30
  local attempt=1

  info "等待 $name 服务启动..."
  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
      success "$name 服务已就绪 (端口 $port)"
      return 0
    fi
    printf "."
    sleep 2
    attempt=$((attempt + 1))
  done
  echo ""
  error "$name 服务启动超时"
  return 1
}

cmd_build() {
  check_docker
  info "构建 Docker 镜像..."
  docker compose -f "$COMPOSE_FILE" build --no-cache
  success "镜像构建完成"
}

cmd_dev() {
  check_docker
  info "启动开发模式（前后端分离，热重载）..."
  docker compose -f "$COMPOSE_FILE" --profile frontend up
}

cmd_up_frontend() {
  warn "前端已集成到后端服务中，只需启动后端即可访问完整界面"
  warn "如需前端热重载开发，使用: docker compose --profile frontend up"
}

cmd_up() {
  check_docker
  info "构建并启动后端服务（包含前端界面）..."
  cmd_build
  OLLAMA_BASE_URL="$OLLAMA_URL" docker compose -f "$COMPOSE_FILE" up -d vibe-trading
  wait_healthy vibe-trading "$BACKEND_PORT" "后端"
  success "服务已启动！"
  cmd_urls
}

cmd_down() {
  check_docker
  info "停止所有服务..."
  docker compose -f "$COMPOSE_FILE" down
  success "所有服务已停止"
}

cmd_restart() {
  check_docker
  info "重启服务..."
  docker compose -f "$COMPOSE_FILE" restart vibe-trading
  wait_healthy vibe-trading "$BACKEND_PORT" "后端"
}

cmd_logs() {
  local service="${1:-}"
  check_docker
  if [ -z "$service" ]; then
    docker compose -f "$COMPOSE_FILE" logs -f
  else
    case "$service" in
      backend) docker compose -f "$COMPOSE_FILE" logs -f vibe-trading ;;
      frontend) docker compose -f "$COMPOSE_FILE" logs -f frontend ;;
      *) docker compose -f "$COMPOSE_FILE" logs -f "$service" ;;
    esac
  fi
}

cmd_status() {
  check_docker
  echo ""
  echo "=== 服务状态 ==="
  docker compose -f "$COMPOSE_FILE" ps
  echo ""
  echo "=== 健康检查 ==="
  if curl -sf "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
    success "后端服务: 健康"
  else
    error "后端服务: 不健康或未启动"
  fi
  echo ""
  cmd_urls
}

cmd_shell() {
  check_docker
  info "进入后端容器 shell..."
  docker compose -f "$COMPOSE_FILE" exec vibe-trading /bin/bash
}

cmd_health() {
  check_docker
  echo "=== 健康检查 ==="
  echo ""
  echo -n "后端服务 (http://localhost:$BACKEND_PORT/health): "
  if curl -sf "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
    success "正常"
  else
    error "异常"
  fi
}

cmd_clean() {
  check_docker
  warn "清理 Docker 资源..."
  read -p "这将删除所有容器、镜像和卷，是否继续? (y/N): " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    docker compose -f "$COMPOSE_FILE" down -v --rmi local
    success "清理完成"
  else
    info "取消清理"
  fi
}

cmd_urls() {
  echo ""
  echo "=== 访问地址（单一端口） ==="
  echo -e "前端界面:  ${GREEN}http://localhost:$BACKEND_PORT${NC}"
  echo -e "API 文档:  ${GREEN}http://localhost:$BACKEND_PORT/docs${NC}"
  echo -e "健康检查:  ${GREEN}http://localhost:$BACKEND_PORT/health${NC}"
  echo ""
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  restart) cmd_restart ;;
  build) cmd_build ;;
  logs) docker compose -f "$COMPOSE_FILE" logs -f ;;
  status) cmd_status ;;
  shell) cmd_shell ;;
  health) cmd_health ;;
  dev) cmd_dev ;;
  clean) cmd_clean ;;
  urls) cmd_urls ;;
  -h|--help|help|"") usage ;;
  *)
    error "未知命令: $1"
    usage >&2
    exit 1
    ;;
esac
