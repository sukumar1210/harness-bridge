#!/usr/bin/env bash
# ==============================================================================
# Harness Bridge - Unified One-Shot Installer
#
# Supported execution forms:
#   1. Remote streaming (curl | bash):
#      curl -fsSL https://raw.githubusercontent.com/sukumar1210/harness-bridge/main/install.sh | bash
#   2. Local execution:
#      ./install.sh [--docker | --local] [--port <port>]
#
# Self-contained with zero relative script dependencies.
# ==============================================================================
set -euo pipefail

REPO="sukumar1210/harness-bridge"
DOCKER_IMAGE="sukumar1210/harness-bridge:latest"
LOCAL_TAG="harness-bridge:latest"
PORT="${PORT:-8000}"
MODE=""
NON_INTERACTIVE=false

# ------------------------------------------------------------------------------
# CLI Argument Parsing
# ------------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --docker|-d)
            MODE="docker"
            NON_INTERACTIVE=true
            shift
            ;;
        --local|-l)
            MODE="local"
            NON_INTERACTIVE=true
            shift
            ;;
        --yes|-y)
            NON_INTERACTIVE=true
            shift
            ;;
        --port|-p)
            PORT="${2:-8000}"
            shift 2
            ;;
        --help|-h)
            cat <<EOF
Harness Bridge Unified One-Shot Installer

Usage:
  install.sh [options]
  curl -fsSL https://.../install.sh | bash -s -- [options]

Options:
  --docker, -d       Install and run as single persistent Docker container over SSE/HTTP.
                     (Zero host Python requirement).
  --local, -l        Install local CLI (~/.local/bin/harness-bridge) running via on-demand stdio.
  -y, --yes          Non-interactive confirmation (uses auto-detected runtime).
  -p, --port <port>  Daemon port for Docker mode (default: 8000).
  -h, --help         Display this help message.

Environment Variables:
  HARNESS_BRIDGE_MODE        Set to 'docker' or 'local' to pre-select runtime.
  HARNESS_BRIDGE_WORKSPACE   Workspace directory mounted to /workspace in Docker.
  PORT                       Port number for Docker container daemon (default: 8000).
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Run with --help for usage." >&2
            exit 1
            ;;
    esac
done

# Check environment variable override
if [ -z "$MODE" ] && [ -n "${HARNESS_BRIDGE_MODE:-}" ]; then
    case "${HARNESS_BRIDGE_MODE,,}" in
        docker) MODE="docker" ;;
        local)  MODE="local" ;;
    esac
fi

# ------------------------------------------------------------------------------
# Interactive / Headless Detection
# ------------------------------------------------------------------------------
# When piped (curl | bash), stdin (fd 0) is the curl pipe, NOT a tty.
# We check if stdout (fd 1) is a tty AND /dev/tty can be opened for reading.
IS_TTY=false
if [ -t 1 ] && (: < /dev/tty) 2>/dev/null; then
    IS_TTY=true
fi

echo "============================================================"
echo "           Harness Bridge One-Shot Installer                "
echo "============================================================"

if [ -z "$MODE" ]; then
    if [ "$IS_TTY" = true ] && [ "$NON_INTERACTIVE" = false ]; then
        echo ""
        echo "Select installation runtime:"
        echo "  1) Docker container (Recommended - persistent container, zero host Python)"
        echo "  2) Local host install (installs harness-bridge CLI into ~/.local/bin via venv)"
        echo ""
        read -r -p "Enter choice [1-2] (default: 1): " choice < /dev/tty || choice="1"
        case "$choice" in
            2|local|Local)
                MODE="local"
                ;;
            *)
                MODE="docker"
                ;;
        esac
    else
        # Headless / CI automated heuristic
        echo "Non-interactive / headless environment detected. Probing host runtimes..."
        if command -v docker &>/dev/null && docker info &>/dev/null; then
            echo "  [✓] Responsive Docker daemon found. Defaulting to Docker runtime."
            MODE="docker"
        elif command -v python3 &>/dev/null; then
            echo "  [✓] Python 3 found on PATH. Defaulting to Local runtime."
            MODE="local"
        else
            echo "Error: Neither a responsive Docker daemon nor python3 was found on PATH." >&2
            echo "Please install Docker or Python 3.11+ before running installation." >&2
            exit 1
        fi
    fi
fi

# ------------------------------------------------------------------------------
# Branch 1: Docker Runtime Installation
# ------------------------------------------------------------------------------
if [ "$MODE" = "docker" ]; then
    echo ""
    echo "=== Installing Harness Bridge (Docker Mode) ==="

    if ! command -v docker &>/dev/null; then
        echo "Error: 'docker' command not found on system PATH." >&2
        echo "Docker is required for container mode." >&2
        if [ "$IS_TTY" = true ] && command -v python3 &>/dev/null; then
            read -r -p "Would you like to fall back to Local Python install? [y/N]: " fb < /dev/tty || fb="n"
            if [[ "$fb" =~ ^[Yy]$ ]]; then
                MODE="local"
            else
                exit 1
            fi
        else
            exit 1
        fi
    fi
fi

if [ "$MODE" = "docker" ]; then
    # Verify docker daemon is responsive
    if ! docker info &>/dev/null; then
        echo "Error: Docker daemon is not running or current user lacks permission to access docker.sock." >&2
        exit 1
    fi

    echo "[1/3] Pulling and tagging image..."
    if docker pull "$DOCKER_IMAGE" 2>/dev/null; then
        docker tag "$DOCKER_IMAGE" "$LOCAL_TAG" 2>/dev/null || true
        echo "  [✓] Image ready: $LOCAL_TAG"
    elif docker image inspect "$LOCAL_TAG" &>/dev/null; then
        echo "  [✓] Using existing local image: $LOCAL_TAG"
    else
        echo "  [!] Could not pull $DOCKER_IMAGE. Checking for local build context..."
        if [ -f "Dockerfile" ]; then
            echo "  Building $LOCAL_TAG from local Dockerfile..."
            docker build -t "$LOCAL_TAG" .
        else
            echo "Error: Unable to pull $DOCKER_IMAGE and no local Dockerfile found." >&2
            exit 1
        fi
    fi

    echo "[2/3] Starting persistent background container..."
    WORKSPACE_MOUNT="${HARNESS_BRIDGE_WORKSPACE:-$PWD}"
    
    # Clean up existing container if stopped or conflicting
    if docker ps -q -f name=^/harness-bridge$ | grep -q .; then
        echo "  Container 'harness-bridge' is already running."
    elif docker ps -aq -f name=^/harness-bridge$ | grep -q .; then
        echo "  Removing stopped container 'harness-bridge'..."
        docker rm -f harness-bridge &>/dev/null || true
        docker run -d \
            --name harness-bridge \
            --restart unless-stopped \
            -p "${PORT}:8000" \
            -v "$WORKSPACE_MOUNT:/workspace" \
            -v harness-bridge-data:/home/bridge/.harness-bridge \
            "$LOCAL_TAG" \
            serve --transport unified --host 0.0.0.0 --port 8000
    else
        docker run -d \
            --name harness-bridge \
            --restart unless-stopped \
            -p "${PORT}:8000" \
            -v "$WORKSPACE_MOUNT:/workspace" \
            -v harness-bridge-data:/home/bridge/.harness-bridge \
            "$LOCAL_TAG" \
            serve --transport unified --host 0.0.0.0 --port 8000
    fi

    echo "[3/3] Verifying container health and registering harnesses..."
    SSE_URL="http://localhost:${PORT}/sse"
    HEALTHY=false
    for i in {1..15}; do
        if curl -s -f -o /dev/null -m 2 "$SSE_URL" 2>/dev/null || \
           curl -s -f -o /dev/null -m 2 "http://localhost:${PORT}/mcp" 2>/dev/null; then
            HEALTHY=true
            break
        fi
        sleep 1
    done

    if [ "$HEALTHY" = true ]; then
        echo "  [✓] Daemon healthy and listening at $SSE_URL"
    else
        echo "  [!] Daemon starting up; proceeding with harness registration..."
    fi

    # Register into Claude Code
    if command -v claude &>/dev/null; then
        claude mcp remove harness-bridge &>/dev/null || true
        if claude mcp add --transport sse -s user harness-bridge "$SSE_URL" &>/dev/null; then
            echo "  [✓] Claude Code: Registered at $SSE_URL"
        fi
    fi

    # Register into Antigravity
    if command -v agy &>/dev/null; then
        agy mcp remove harness-bridge &>/dev/null || true
        if agy mcp add harness-bridge "$SSE_URL" &>/dev/null; then
            echo "  [✓] Antigravity CLI: Registered at $SSE_URL"
        fi
    fi

    # Direct fallback JSON update
    CLAUDE_JSON="${HOME}/.claude.json"
    if [ -f "$CLAUDE_JSON" ] || [ -d "${HOME}/.claude" ]; then
        if command -v python3 &>/dev/null; then
            python3 -c "
import json
p = '$CLAUDE_JSON'
url = '$SSE_URL'
try:
    with open(p, 'r') as f: data = json.load(f)
except Exception: data = {}
data.setdefault('mcpServers', {})['harness-bridge'] = {'type': 'sse', 'url': url}
with open(p, 'w') as f: json.dump(data, f, indent=2)
" &>/dev/null || true
        fi
    fi

    AGY_JSON="${HOME}/.gemini/config/mcp_config.json"
    if [ -f "$AGY_JSON" ] || [ -d "${HOME}/.gemini" ]; then
        if command -v python3 &>/dev/null; then
            python3 -c "
import json
p = '$AGY_JSON'
url = '$SSE_URL'
try:
    with open(p, 'r') as f: data = json.load(f)
except Exception: data = {}
data.setdefault('mcpServers', {})['harness-bridge'] = {'url': url}
with open(p, 'w') as f: json.dump(data, f, indent=2)
" &>/dev/null || true
        fi
    fi

    echo ""
    echo "============================================================"
    echo "  Installation Complete! Harness Bridge Docker daemon is live."
    echo "  Container : harness-bridge (docker ps)"
    echo "  Endpoint  : $SSE_URL"
    echo "============================================================"
    exit 0
fi

# ------------------------------------------------------------------------------
# Branch 2: Local Host CLI Installation
# ------------------------------------------------------------------------------
if [ "$MODE" = "local" ]; then
    echo ""
    echo "=== Installing Harness Bridge (Local Host Mode) ==="

    if ! command -v python3 &>/dev/null; then
        echo "Error: python3 is required for local installation but was not found on PATH." >&2
        exit 1
    fi

    # Verify Python version >= 3.11
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
        echo "Error: Python 3.11+ is required (found Python $PY_VER)." >&2
        exit 1
    fi

    INSTALL_DIR="${HOME}/.harness-bridge"
    VENV_DIR="${INSTALL_DIR}/venv"
    BIN_DIR="${HOME}/.local/bin"

    mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

    echo "[1/3] Setting up isolated Python virtual environment..."
    if [ ! -d "${VENV_DIR}" ]; then
        python3 -m venv "${VENV_DIR}"
    fi

    echo "[2/3] Installing Harness Bridge package..."
    # If running inside repo checkout, install local package
    if [ -f "pyproject.toml" ] && grep -q "harness_bridge" pyproject.toml 2>/dev/null; then
        echo "  Installing from local repository checkout..."
        "${VENV_DIR}/bin/pip" install --upgrade --quiet -e .
    else
        # Remote execution: fetch latest wheel or git repo
        RELEASE_JSON=$(curl -sSL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null || true)
        WHEEL_URL=$(echo "${RELEASE_JSON}" | grep -o 'https://[^"]*harness_bridge[^"]*\.whl' | head -n 1 || true)
        if [ -n "${WHEEL_URL}" ]; then
            echo "  Downloading latest release wheel from GitHub..."
            TMP_WHL=$(mktemp 2>/dev/null || mktemp -t 'hb')
            curl -sSL "${WHEEL_URL}" -o "${TMP_WHL}.whl"
            "${VENV_DIR}/bin/pip" install --upgrade --quiet "${TMP_WHL}.whl"
            rm -f "${TMP_WHL}" "${TMP_WHL}.whl"
        else
            echo "  Installing latest package from repository..."
            "${VENV_DIR}/bin/pip" install --upgrade --quiet "git+https://github.com/${REPO}.git"
        fi
    fi

    # Symlink CLI binary into ~/.local/bin
    ln -sf "${VENV_DIR}/bin/harness-bridge" "${BIN_DIR}/harness-bridge"
    echo "  [✓] Executable linked: ${BIN_DIR}/harness-bridge"

    echo "[3/3] Registering Harness Bridge in AI agent harnesses (stdio mode)..."
    # Execute the installed Python setup command directly (delegation)
    "${BIN_DIR}/harness-bridge" setup

    echo ""
    echo "============================================================"
    echo "  Installation Complete! Local host runtime configured."
    echo "  Executable : ${BIN_DIR}/harness-bridge"
    echo "  Transport  : stdio (on-demand child process, zero idle daemon)"
    if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
        echo "  Note       : Ensure ${BIN_DIR} is in your PATH:"
        echo "               export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    echo "============================================================"
    exit 0
fi
