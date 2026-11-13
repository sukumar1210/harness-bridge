# Design: Aggregated Sessions, Workspace Boundary Enforcement & Remote Duplex Gateway

* **Author:** Sukumar Rastogi (`sukumar1210`)
* **Date:** 2026-11-11
* **Status:** In Review (Drafting Phase)
* **Target Release:** Harness Bridge v0.2.0

---

## 1. Overview & Problem Statement

### 1.1 The Problem
AI coding harnesses—such as Claude Code and Google Antigravity CLI (`agy`)—operate in isolated, single-tenant silos. Current agent workflows face three primary architectural barriers:

1. **Siloed Agent Execution**: When an orchestrator delegates tasks across multiple harnesses (e.g., Claude Code for frontend components, Antigravity for deep codebase auditing), each harness operates as a disconnected subprocess without peer visibility or direct communication channels.
2. **Workspace & Filesystem Integrity Hazards**: Without workspace boundary enforcement, multiple agents dispatched concurrently onto the same repository root risk race conditions, git lock contention (`.git/index.lock`), and file clobbering. Furthermore, agents coordinating across separate machines cannot safely share direct file paths without verified device-local collocation.
3. **Lack of Remote Duplex Control**: Developers cannot monitor, guide, or send commands to active agent swarms from a mobile phone, tablet, or external cloud session. Standard MCP stdio transports are tied directly to the local terminal, preventing bidirectional remote interaction.

### 1.2 Proposed Solution Overview
Harness Bridge introduces **Aggregated Sessions**: federated coordination rooms where multiple agent sessions—spanning different harnesses, repositories, and devices—can join a shared communication bus. The bridge enforces strict workspace scope rules (device-local single-project vs. registered multi-project allowlists), provides stable peer addressing (`<device_id>/<harness>/<session_id>`), and exposes an authenticated remote transport gateway for duplex mobile and cloud control.

---

## 2. Goals & Non-Goals

### 2.1 In-Scope Goals
* **Aggregated Session Rooms**: Group multiple independent agent sessions under a single logical identifier (`aggregated_session_id`) with member state tracking and inboxes.
* **Stable Composite Addressing**: Identify participating agents via `<device_id>/<harness>/<session_id>`, using hardware/OS fingerprints (hostname + machine ID) rather than volatile IP addresses.
* **Peer Presence & Discovery**: Provide MCP tools for agents to query active room members (`bridge_list_peers`), inspect their active working directory, and check heartbeat status.
* **Duplex Peer-to-Peer & Broadcast Messaging**: Provide MCP tools (`bridge_send_peer_message`, `bridge_broadcast_message`, `bridge_get_messages`) for asynchronous inter-agent coordination.
* **Workspace Boundary Enforcement**:
  * *Strict Single-Project Mode (Default)*: Require all participating agents to reside on the same physical host (`device_id`) and within the same repository root or child worktrees (`.worktrees/`).
  * *Multi-Project Allowlist Mode*: Validate connecting agents against an explicit allowlist of permitted project directories, enabling cross-service coordination without cross-codebase corruption.
* **Remote Gateway Transport**: Expose a secure, token-authenticated network transport (Server-Sent Events / Streamable HTTP and WebSocket backchannel) enabling remote mobile and cloud clients to send duplex commands and stream session events.

### 2.2 Out-of-Scope Non-Goals
* **Distributed File Synchronization**: The bridge will not sync file bytes across network machines. Cross-device agents coordinate via messages, diffs, or git remotes; filesystem sharing is strictly device-local.
* **Proprietary Mobile App Development**: The bridge provides standardized MCP endpoints and a lightweight web dashboard, avoiding native iOS/Android client maintenance.
* **Autonomous Conflict Resolution**: The bridge does not arbitrate conflicting code changes between two agents editing the same branch; isolation is achieved through ephemeral git worktrees.

---

## 3. Technical Plan & Architecture

### 3.1 Architectural Diagram

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              Remote Duplex Clients                                     │
│  ┌───────────────────────────────┐          ┌───────────────────────────────────────┐  │
│  │ Mobile Browser / PWA Dashboard│          │ Cloud Orchestration Session / Worker  │  │
│  └───────────────┬───────────────┘          └───────────────────┬───────────────────┘  │
└──────────────────┼──────────────────────────────────────────────┼──────────────────────┘
                   │ WSS / Authenticated SSE Backchannel          │ HTTPS / Bearer Token
                   ▼                                              ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          Harness Bridge Gateway & Hub                                  │
│ ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ Remote Gateway Layer: FastAPI/Starlette SSE + WebSocket Server (--port 8765)       │ │
│ │ Authentication Guard: Bearer Token / mTLS Header Validation                        │ │
│ ├────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ Aggregated Session Bus:                                                            │ │
│ │  - Room Registry (aggregated_session_id)                                           │ │
│ │  - Member Heartbeat & Presence Store                                               │ │
│ │  - Peer Message Inboxes & FIFO Broadcast Queues                                    │ │
│ ├────────────────────────────────────────────────────────────────────────────────────┤ │
│ │ Workspace Scope & Boundary Enforcer:                                               │ │
│ │  - Mode A: Strict Single-Project (assert same device_id && same repo/worktree)     │ │
│ │  - Mode B: Multi-Project Allowlist (assert cwd in allowed_project_roots)           │ │
│ └──────────────────────────────────────┬─────────────────────────────────────────────┘ │
└────────────────────────────────────────┼───────────────────────────────────────────────┘
                                         │ Local Stdio MCP / Subprocess Spawner
                   ┌─────────────────────┴──────────────────────┐
                   ▼                                            ▼
┌──────────────────────────────────────┐     ┌───────────────────────────────────────┐
│ Local Worker Session: Claude Code    │     │ Local Worker Session: Antigravity CLI │
│ - Host: devbox-linux                 │     │ - Host: devbox-linux                  │
│ - Peer: devbox/claude/sess-1         │     │ - Peer: devbox/agy/sess-2             │
│ - Worktree: .worktrees/sess-1        │     │ - Worktree: .worktrees/sess-2         │
└──────────────────────────────────────┘     └───────────────────────────────────────┘
```

### 3.2 Core Component Architecture

#### 1. Device Identification Layer (`DeviceIdentifier`)
To address peers across reboots and dynamic IP shifts, each node computes a deterministic, persistent device identifier:
* **Linux**: Read from `/etc/machine-id` (fallback `/var/lib/dbus/machine-id`), combined with `platform.node()`.
* **macOS**: `IOPlatformUUID` extracted via `ioreg -rd1 -c IOPlatformExpertDevice`.
* **Windows**: Cryptographic Machine GUID read from registry `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`.
* **Fallback**: SHA-256 hash of network MAC address + user hostname.
* **Friendly Name Override**: Configurable via `HARNESS_BRIDGE_DEVICE_NAME` (e.g. `gpu-workstation`, `macbook-pro`).

#### 2. Composite Peer Addressing (`PeerAddress`)
Every agent session connecting to an aggregated room receives an immutable composite address:
```
<device_id>/<harness>/<session_id>
```
* **Host/Device**: `devbox-linux`
* **Harness**: `claude` | `agy`
* **Session**: UUID or named session string
* **Validation**: Collocation requirements check `peer_a.device_id == peer_b.device_id`.

#### 3. Workspace Boundary Enforcer (`WorkspacePolicy`)
When an agent invokes `bridge_join_session(aggregated_session_id, working_directory)`, the enforcer validates admittance against the room's policy:
* **`strict_single_project` (Default)**:
  1. Room records the root repository canonical path upon creation.
  2. Admitted sessions MUST match the room's `device_id`.
  3. Admitted session `working_directory` must equal the root repo or resolve inside `.worktrees/<session_id>` under that root.
  4. Any session from an external path or different device is rejected with `WorkspacePolicyViolationError`.
* **`multi_project_allowlist`**:
  1. Room maintains a list of canonical paths `allowed_project_roots: list[str]`.
  2. Admitted sessions must have `working_directory` equal to or inside one of the allowlisted paths.
  3. Enables controlled cross-repository communication without arbitrary filesystem leakage.

#### 4. Peer Message Bus & Inboxes (`PeerMessageBus`)
* **Message Delivery**:
  * Direct Message (`bridge_send_peer_message`): Appends a structured `PeerMessage` to the target peer's FIFO inbox.
  * Broadcast Message (`bridge_broadcast_message`): Appends the message to all active peer inboxes within the aggregated session except the sender.
* **Message Schema**:
  ```python
  class PeerMessage(BaseModel):
      message_id: str
      aggregated_session_id: str
      sender: str  # <device_id>/<harness>/<session_id>
      recipient: str | None  # None for broadcast
      message_type: Literal["text", "task_handover", "artifact", "control"]
      content: str
      metadata: dict[str, Any] = Field(default_factory=dict)
      timestamp: float
  ```
* **Message Ingestion During Headless Turns**:
  * Agents query unread messages using `bridge_get_messages`.
  * For dispatched turns coordinated through `SessionManager`, pending messages are automatically prepended as high-priority system context blocks into the subsequent prompt invocation.

#### 5. Remote Gateway & Duplex Transport (`RemoteGatewayServer`)
* **Transport Protocol**: Exposes dual transport over HTTP/HTTPS:
  * **SSE Stream (`GET /api/v1/sessions/{id}/events`)**: Push session events, agent outputs, and peer messages in real time.
  * **Command Endpoint (`POST /api/v1/sessions/{id}/commands`)**: Send duplex control instructions, prompts, or messages to specific sessions.
  * **WebSocket Hub (`GET /api/v1/sessions/{id}/ws`)**: Full-duplex connection for mobile and terminal clients.
* **Authentication**: Enforces HTTP Bearer Token authentication (`--auth-token <secret>`). Rejects unauthenticated connections with 401 Unauthorized before any command parsing.

---

### 3.3 New Model Context Protocol (MCP) Tools

| Tool Name | Arguments | Description |
| :--- | :--- | :--- |
| `bridge_join_session` | `aggregated_session_id: str`, `working_directory: str`, `mode: str = "strict_single_project"` | Adopts or creates an aggregated session room and validates workspace boundaries. |
| `bridge_leave_session` | `aggregated_session_id: str` | Gracefully removes the session from the room and deregisters presence. |
| `bridge_list_peers` | `aggregated_session_id: str` | Returns all active peers, their harness, host device, working directory, and last heartbeat. |
| `bridge_send_peer_message` | `aggregated_session_id: str`, `target_peer_id: str`, `content: str`, `message_type: str = "text"` | Sends a targeted message to an active peer session. |
| `bridge_broadcast_message` | `aggregated_session_id: str`, `content: str` | Broadcasts an announcement or coordination message to all members in the room. |
| `bridge_get_messages` | `aggregated_session_id: str`, `limit: int = 20`, `mark_as_read: bool = True` | Retrieves incoming peer messages from the calling session's inbox. |

---

## 4. Alternatives Considered

### 4.1 Ephemeral IP & MAC Addressing vs. Deterministic Machine ID Fingerprinting
* **Alternative Explored**: Use device IP addresses (e.g. `192.168.1.100:8765`) or hardware MAC addresses as the primary peer network identifier.
* **Why Rejected**: *Rejected by author*: Dynamic IP addresses shift frequently across DHCP leases, mobile network switches (cellular vs. Wi-Fi), and virtual interfaces, causing peer address invalidation and routing failures mid-session. MAC addresses are frequently masked, randomized, or virtualized in modern OS and containerized environments. Using deterministic OS-level machine IDs (`/etc/machine-id`, registry GUIDs) guarantees stable hardware identity across reboots and network transitions.

### 4.2 Unrestricted Global Directory Access vs. Strict Collocation & Allowlist
* **Alternative Explored**: Allow any remote or local agent to join an aggregated session regardless of working directory or host device.
* **Why Rejected**: *Rejected by author*: Allowing agents residing on different devices or operating on arbitrary filesystem paths to collaborate on a single codebase creates severe synchronization conflicts, git lock contention (`.git/index.lock`), and uncommitted file clobbering. Enforcing same-device collocation for single-project worktree sessions and requiring explicit directory allowlists for multi-project workflows guarantees workspace integrity.

### 4.3 Live Bidirectional PTY Pipes vs. Headless Subprocess Turns with Asynchronous Inboxes
* **Alternative Explored**: Maintain persistent, live pseudo-terminal (PTY) streaming pipes (`claude --input-format stream-json --output-format stream-json`) to inject mid-flight keystrokes while an agent is executing.
* **Why Rejected**: *Rejected by author*: Bidirectional live streaming pipes across diverse LLM CLIs are brittle, prone to deadlock on large outputs, vulnerable to pipe buffer saturation (64KB limits on Linux), and leave zombie daemon processes when terminal sessions drop. Decoupled headless subprocess turns with native session resumption flags (`--resume`, `--conversation`) paired with FIFO message inboxes provide deterministic lifecycle stability.

### 4.4 Unauthenticated Public Ingress vs. Token-Gated Gateway with Overlay Ingress
* **Alternative Explored**: Expose an open HTTP/WebSocket listener on all network interfaces (`0.0.0.0`) without authentication to make remote mobile access simple.
* **Why Rejected**: *Rejected by author*: AI coding harnesses run with permission bypass flags (`--dangerously-skip-permissions`). Unauthenticated network exposure would create a critical Remote Code Execution (RCE) vulnerability on the developer's workstation. Enforcing cryptographic Bearer token authentication and recommending overlay networks (Tailscale/WireGuard) or outbound reverse tunnels guarantees zero-trust remote access.

---

## 5. Detailed Implementation Plan

This section enumerates every file that will be created, modified, or updated to deliver Aggregated Sessions, Workspace Boundary Enforcement, and the Remote Duplex Gateway.

### 5.1 Enumerate Files Touched & Created

#### 1. Core Schemas & Types: `harness_bridge/core/types.py`
* **Changes**: Add new Pydantic models:
  * `WorkspacePolicyMode = Literal["strict_single_project", "multi_project_allowlist", "open"]`
  * `PeerAddress(device_id: str, harness: str, session_id: str)`
  * `PeerMessage(message_id: str, aggregated_session_id: str, sender: str, recipient: str | None, message_type: str, content: str, timestamp: float)`
  * `AggregatedSessionInfo(aggregated_session_id: str, primary_root: str, policy: WorkspacePolicyMode, allowed_paths: list[str], members: dict[str, PeerAddress], created_at: float)`
* **Rationale**: Establishes strict data structures for message transport, peer addressing, and room state tracking.

#### 2. Device Fingerprinting: `harness_bridge/core/device.py` (New File)
* **Changes**: Implement `get_device_id() -> str`:
  * Detects Linux `/etc/machine-id`, macOS `IOPlatformUUID`, and Windows registry `MachineGuid`.
  * Provides fallback to hashed hardware MAC + node hostname.
  * Honors `HARNESS_BRIDGE_DEVICE_NAME` environment variable override.
* **Rationale**: Guarantees deterministic, persistent device addresses without relying on volatile IP addresses.

#### 3. Domain Exceptions: `harness_bridge/core/exceptions.py`
* **Changes**: Add:
  * `WorkspacePolicyViolationError`: Raised when an agent attempts to join a session from an unauthorized directory or different device.
  * `PeerNotFoundError`: Raised when dispatching a direct message to a nonexistent or disconnected peer.
  * `AggregatedSessionNotFoundError`: Raised on operations against invalid room IDs.
  * `GatewayAuthError`: Raised when remote clients fail Bearer token authentication.
* **Rationale**: Provides granular error reporting and protocol exception handling.

#### 4. Aggregated Session Bus & Inboxes: `harness_bridge/session/aggregated.py` (New File)
* **Changes**: Implement:
  * `AggregatedSessionManager`: Manages room registration, member presence leases, and workspace admittance validation.
  * `PeerMessageBus`: Thread-safe FIFO inboxes for direct messages and room-wide broadcast queues with message TTL pruning.
* **Rationale**: Serves as the central coordination hub managing peer presence and message routing.

#### 5. Turn Context Injection: `harness_bridge/session/manager.py`
* **Changes**: Update `SessionManager.execute_task`:
  * Before launching a subprocess turn, checks if the session belongs to an aggregated room.
  * Pulls pending unread peer messages from `PeerMessageBus` and automatically formats them as system prompt context blocks prepended to the prompt.
* **Rationale**: Enables headless agents (`claude -p`, `agy -p`) to ingest peer communications across turns without requiring live PTY streaming.

#### 6. Remote Duplex Gateway: `harness_bridge/server/gateway.py` (New File)
* **Changes**: Implement an ASGI application (using Starlette/Uvicorn):
  * `GET /api/v1/sessions/{id}/events`: SSE endpoint streaming real-time room events and peer outputs.
  * `POST /api/v1/sessions/{id}/commands`: HTTP endpoint for remote prompt and message dispatch.
  * `GET /api/v1/sessions/{id}/ws`: Duplex WebSocket endpoint for continuous bidirectional communication.
  * Middleware enforcing Bearer token authentication against `HARNESS_BRIDGE_AUTH_TOKEN`.
* **Rationale**: Provides mobile devices, browser dashboards, and cloud sessions with secure duplex access to local agent sessions.

#### 7. MCP Server Tool Registration: `harness_bridge/server/mcp_server.py`
* **Changes**: Register the 6 new MCP tools:
  * `bridge_join_session`
  * `bridge_leave_session`
  * `bridge_list_peers`
  * `bridge_send_peer_message`
  * `bridge_broadcast_message`
  * `bridge_get_messages`
* **Rationale**: Exposes aggregated session coordination directly to LLM harnesses via native MCP tool calls.

#### 8. CLI Application Commands: `harness_bridge/cli/main.py`
* **Changes**:
  * Update `serve` command to support `--transport sse` and `--transport ws`, `--port <int>`, `--host <str>`, and `--auth-token <secret>`.
  * Add `session` subcommands: `harness-bridge session list`, `harness-bridge session show <id>`.
  * Add `msg` subcommands: `harness-bridge msg send <room_id> <target> <content>`, `harness-bridge msg broadcast <room_id> <content>`.
* **Rationale**: Enables human operators to inspect rooms, monitor swarms, and broadcast commands directly from the terminal.

#### 9. Dependency Specification: `pyproject.toml`
* **Changes**: Add `starlette>=0.38.0` and `uvicorn>=0.30.0` to project dependencies.
* **Rationale**: Provides production-grade ASGI HTTP/SSE/WebSocket server capabilities without heavy frameworks.

#### 10. Automated Test Suite: `tests/`
* **`tests/test_device.py` (New File)**: Verifies deterministic device ID resolution across OS environments and environment overrides.
* **`tests/test_aggregated_session.py` (New File)**: Tests room creation, member joining, workspace boundary enforcement (asserts rejection of outside directories and mismatched devices in single-project mode), and heartbeat expiry.
* **`tests/test_peer_messaging.py` (New File)**: Tests direct message delivery to inboxes, broadcast fan-out, message FIFO ordering, and context prepending in `SessionManager`.
* **`tests/test_gateway.py` (New File)**: Tests SSE event streams, WebSocket duplex messaging, and 401 unauthorized rejections.
* **Rationale**: Guarantees test-driven quality and regression protection across all newly introduced components.

#### 11. Documentation: `README.md`
* **Changes**: Add architectural guide for Aggregated Sessions, remote gateway setup commands, network security recommendations (Tailscale/Cloudflare), and new MCP tool documentation.
* **Rationale**: Ensures users and contributors have clear instructions on configuring multi-agent rooms and remote access.

---

### 5.2 Phased Rollout Sequence

1. **Phase 1: Addressing & Workspace Boundary Enforcement**
   * Implement `DeviceIdentifier` (`harness_bridge/core/device.py`) and new schemas in `harness_bridge/core/types.py`.
   * Implement `AggregatedSessionManager` with workspace policy validation.
   * Unit test boundary enforcement in `tests/test_aggregated_session.py`.

2. **Phase 2: Local Inter-Agent Messaging**
   * Implement `PeerMessageBus` and connect it to `SessionManager` turn context injection.
   * Implement and test the 6 MCP tools in `harness_bridge/server/mcp_server.py`.
   * Unit test peer messaging in `tests/test_peer_messaging.py`.

3. **Phase 3: Remote Duplex Gateway**
   * Implement `RemoteGatewayServer` in `harness_bridge/server/gateway.py`.
   * Wire CLI options in `harness_bridge/cli/main.py`.
   * Unit test HTTP/SSE/WebSocket endpoints and token authentication in `tests/test_gateway.py`.

4. **Phase 4: Documentation & Release**
   * Update `README.md` and release notes.
   * Run full test matrix and linting verification.
