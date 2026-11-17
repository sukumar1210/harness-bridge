# Running Harness Bridge in Docker (Local & Production)

Harness Bridge provides a unified Docker container designed to run seamlessly both for **local development** and in **production environments**.

---

## 1. Quick Start

### Run via Docker Hub (No Source Code Needed)
```bash
docker run -d \
  --name harness-bridge \
  --restart unless-stopped \
  -p 8000:8000 \
  -v "$PWD":/workspace \
  -v harness-bridge-data:/home/bridge/.harness-bridge \
  sukumar1210/harness-bridge:latest
```

### Build from Source
```bash
docker build -t harness-bridge:latest .
```

---

## 2. Local Developer Workflows

### Automated One-Shot Setup (Zero Python Required)
Run the automated Docker setup script:
```bash
./install.sh --docker
```
This single command:
1. Starts the `harness-bridge` background container via `docker compose up -d`.
2. Automatically registers the SSE endpoint (`http://localhost:8000/sse`) in Claude Code and Antigravity.
3. Requires zero Python dependencies or virtual environments on your host.

---

### Manual Setup via Docker Compose (Recommended)
Run Harness Bridge as a long-running background service using Docker Compose:

```bash
docker compose up -d
```

The container exposes:
- **SSE Endpoint**: `http://localhost:8000/sse`
- **Messages Endpoint**: `http://localhost:8000/messages/`
- **Streamable HTTP Endpoint**: `http://localhost:8000/mcp`

Register the SSE endpoint in your installed harnesses:
```bash
# Claude Code
claude mcp add --transport sse -s user harness-bridge http://localhost:8000/sse

# Antigravity CLI
agy mcp add harness-bridge http://localhost:8000/sse
```

Or configure manually in `~/.claude.json` / `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "harness-bridge": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

> [!NOTE]
> All local sessions and subagents multiplex through this single shared daemon container. Unlike ephemeral stdio execution, this guarantees that subagents, concurrent turns, and session resumes never spawn zombie container instances.

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
