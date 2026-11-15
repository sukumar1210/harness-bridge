# Running Harness Bridge in Docker (Local & Production)

Harness Bridge provides a unified Docker container designed to run seamlessly both for **local development** and in **production environments**.

---

## 1. Quick Start

### Build the Image
```bash
docker build -t harness-bridge:latest .
```

### Run CLI Commands
```bash
# Check version
docker run --rm harness-bridge:latest version

# List supported harnesses in the container
docker run --rm harness-bridge:latest list
```

---

## 2. Local Developer Workflows

### Mode A: Stdio MCP Mode (Claude Desktop, Cursor, Windsurf)
In stdio mode, your local MCP client communicates directly with the containerized Harness Bridge over stdin/stdout.

Add to your MCP configuration (e.g. `claude_desktop_config.json` or `~/.claude.json`):
```json
{
  "mcpServers": {
    "harness-bridge": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v", "${workspaceFolder}:/workspace",
        "-v", "harness-bridge-sessions:/home/bridge/.harness-bridge",
        "-e", "ANTHROPIC_API_KEY",
        "harness-bridge:latest",
        "serve",
        "--transport", "stdio"
      ]
    }
  }
}
```

### Mode B: Network Mode with Docker Compose (SSE / HTTP)
Run Harness Bridge as a long-running background service using Docker Compose:

```bash
docker compose up -d
```

The container exposes:
- **SSE Endpoint**: `http://localhost:8000/sse`
- **Messages Endpoint**: `http://localhost:8000/messages/`
- **Streamable HTTP Endpoint**: `http://localhost:8000/mcp`

Configure your MCP client to connect via Server-Sent Events (SSE):
```json
{
  "mcpServers": {
    "harness-bridge": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

---

## 3. Production Deployment

### Docker Run (Standalone Container)
```bash
docker run -d \
  --name harness-bridge \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /var/data/repos:/workspace \
  -v /var/data/harness-bridge:/home/bridge/.harness-bridge \
  -e ANTHROPIC_API_KEY="sk-ant-..." \
  -e GEMINI_API_KEY="..." \
  harness-bridge:latest \
  serve --transport sse --host 0.0.0.0 --port 8000
```

### Kubernetes Pod / Deployment Spec
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: harness-bridge
  labels:
    app: harness-bridge
spec:
  replicas: 1
  selector:
    matchLabels:
      app: harness-bridge
  template:
    metadata:
      labels:
        app: harness-bridge
    spec:
      containers:
        - name: harness-bridge
          image: harness-bridge:latest
          args: ["serve", "--transport", "sse", "--host", "0.0.0.0", "--port", "8000"]
          ports:
            - containerPort: 8000
          env:
            - name: HARNESS_BRIDGE_STORAGE_DIR
              value: "/data/sessions"
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: harness-bridge-secrets
                  key: anthropic-api-key
          volumeMounts:
            - name: session-data
              mountPath: /data
      volumes:
        - name: session-data
          persistentVolumeClaim:
            claimName: harness-bridge-pvc
```

---

## 4. Environment Variables Reference

| Variable | Description | Default |
|---|---|---|
| `HARNESS_BRIDGE_STORAGE_DIR` | Absolute path where multi-turn session journals are stored | `/home/bridge/.harness-bridge/sessions` |
| `WORKSPACE_DIR` | Working directory where target repositories are mounted | `/workspace` |
| `HOST` | Host address to bind for network transports | `0.0.0.0` |
| `PORT` | Network port for SSE/HTTP transports | `8000` |
| `ANTHROPIC_API_KEY` | API key forwarded to Claude Code CLI harness | None |
| `GEMINI_API_KEY` | API key forwarded to Gemini / Antigravity CLI | None |
| `HARNESS_BRIDGE_MAX_HOPS` | Circuit-breaker recursion limit for agent delegation | `10` |

---

## 5. Security & Isolation Invariants

- **Non-Root Runtime**: Runs under dedicated user `bridge` (UID 1000, GID 1000).
- **Git Safe Directory**: Configured with `git config --system --add safe.directory '*'` so host volume checkouts with different UIDs/GIDs mount without permission denial.
- **Process Group Isolation**: Subprocess executions detach via `start_new_session=True` (`setsid()`), isolating signals and ensuring child turns terminate cleanly on timeout or cancellation.
