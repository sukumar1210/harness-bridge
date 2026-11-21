# Multi-stage production and developer Dockerfile for Harness Bridge
FROM python:3.12-slim-bookworm AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install essential system dependencies: git (for worktrees), curl, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x LTS for Claude Code CLI (@anthropic-ai/claude-code)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable python package resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Ensure git safe.directory covers all mounted volumes regardless of host UID/GID
RUN git config --system --add safe.directory '*'

# Create non-root bridge user (UID 1000, GID 1000) for secure container runtime
RUN groupadd -g 1000 bridge && \
    useradd -u 1000 -g bridge -m -s /bin/bash bridge && \
    mkdir -p /workspace /app /home/bridge/.harness-bridge && \
    chown -R bridge:bridge /workspace /app /home/bridge

WORKDIR /app

# Copy project metadata, dependencies, application source, and entrypoint
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY harness_bridge ./harness_bridge
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Install harness-bridge and all dependencies into system environment
RUN uv pip install --system --no-cache -e .

# Configure workspace and storage directory
ENV HARNESS_BRIDGE_STORAGE_DIR=/home/bridge/.harness-bridge/sessions \
    WORKSPACE_DIR=/workspace \
    PORT=8000 \
    HOST=0.0.0.0

LABEL org.opencontainers.image.title="Harness Bridge" \
      org.opencontainers.image.description="Lightweight inter-agent proxy and Model Context Protocol (MCP) server" \
      org.opencontainers.image.source="https://github.com/sukumar1210/harness-bridge" \
      org.opencontainers.image.licenses="MIT"

USER bridge
WORKDIR /workspace

EXPOSE 8000

# Periodic healthcheck verifies MCP server health and responsiveness on SSE endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/sse || python3 -c "import harness_bridge" || exit 1

# Default entrypoint runs smart auto-discovery entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["serve", "--transport", "unified", "--host", "0.0.0.0", "--port", "8000"]
