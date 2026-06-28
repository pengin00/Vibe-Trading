#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper. MCP local management now lives in scripts/local-services.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_SERVICES="$SCRIPT_DIR/local-services"

case "${1:-}" in
  start)
    exec "$LOCAL_SERVICES" mcp-stdio
    ;;
  start-sse)
    exec "$LOCAL_SERVICES" mcp
    ;;
  start-docker)
    shift || true
    echo "scripts/mcp.sh start-docker is deprecated; use docker compose directly or scripts/local-services start." >&2
    exec docker compose -f "$SCRIPT_DIR/../docker-compose.yml" exec vibe-trading python /app/agent/mcp_server.py --transport "${1:-sse}" --port "${2:-${VIBE_MCP_PORT:-8900}}"
    ;;
  stop)
    exec "$LOCAL_SERVICES" stop
    ;;
  status)
    exec "$LOCAL_SERVICES" status
    ;;
  config)
    exec "$LOCAL_SERVICES" mcp-config
    ;;
  test)
    exec "$LOCAL_SERVICES" mcp-test
    ;;
  -h|--help|help|"")
    cat <<USAGE
scripts/mcp.sh is now a compatibility wrapper.

Use scripts/local-services instead:
  scripts/local-services start       # Postgres + backend + MCP SSE
  scripts/local-services mcp         # MCP SSE only
  scripts/local-services mcp-stdio   # MCP stdio foreground
  scripts/local-services mcp-config  # client config examples
  scripts/local-services mcp-test    # smoke test
USAGE
    ;;
  *)
    echo "unknown command: $1" >&2
    echo "try: scripts/local-services --help" >&2
    exit 2
    ;;
esac
