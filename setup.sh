#!/usr/bin/env bash
# ==============================================================================
# Harness Bridge - Idempotent Setup & Re-Registration Script
#
# Use this script to re-configure or repair Harness Bridge MCP registration
# in installed agent harnesses (Claude Code, Antigravity CLI).
# ==============================================================================
set -euo pipefail

PORT="${PORT:-8000}"
USE_DOCKER=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker|-d)
            USE_DOCKER=true
            shift
            ;;
        --local|-l)
            USE_DOCKER=false
            shift
            ;;
        --port|-p)
            PORT="${2:-8000}"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--docker | --local] [--port <port>]"
            echo "  --docker, -d   Register harnesses against Docker container daemon (http://localhost:8000/sse)."
            echo "  --local, -l    Register harnesses using local host CLI (stdio transport)."
            echo "  --port, -p     Port for Docker container daemon (default: 8000)."
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

SSE_URL="http://localhost:${PORT}/sse"

# Auto-detect if container is running when neither flag is explicitly set
if [ "$USE_DOCKER" = false ]; then
    if command -v docker &>/dev/null && docker ps -q -f name=^/harness-bridge$ | grep -q .; then
        USE_DOCKER=true
    fi
fi

echo "============================================================"
echo "           Harness Bridge Setup & Re-Registration           "
echo "============================================================"

if [ "$USE_DOCKER" = true ]; then
    echo "Configuring harnesses for Docker runtime (${SSE_URL})..."
    
    # Claude Code
    if command -v claude &>/dev/null; then
        claude mcp remove harness-bridge &>/dev/null || true
        if claude mcp add --transport sse -s user harness-bridge "$SSE_URL" &>/dev/null; then
            echo "  [✓] Claude Code: Successfully registered at $SSE_URL"
        fi
    fi

    # Antigravity CLI
    if command -v agy &>/dev/null; then
        agy mcp remove harness-bridge &>/dev/null || true
        if agy mcp add harness-bridge "$SSE_URL" &>/dev/null; then
            echo "  [✓] Antigravity CLI: Successfully registered at $SSE_URL"
        fi
    fi

    echo ""
    echo "Setup complete (Docker SSE endpoint: ${SSE_URL})."
    exit 0
fi

# Local stdio mode: delegate directly to Python setup engine
echo "Configuring harnesses for local host runtime (stdio transport)..."
if command -v harness-bridge &>/dev/null; then
    harness-bridge setup
elif [ -x "${HOME}/.local/bin/harness-bridge" ]; then
    "${HOME}/.local/bin/harness-bridge" setup
elif [ -x "${HOME}/.harness-bridge/venv/bin/harness-bridge" ]; then
    "${HOME}/.harness-bridge/venv/bin/harness-bridge" setup
else
    echo "Error: harness-bridge CLI executable not found." >&2
    echo "Please run './install.sh' first to install Harness Bridge." >&2
    exit 1
fi

echo ""
echo "Setup complete (Local stdio transport)."
