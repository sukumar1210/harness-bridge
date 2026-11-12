# Goldfish Annotated Review Report (Round 5)

* **Target:** `docs/designs/roles_teams_and_presets.md` (`Lines 1-685`)
* **Status:** Resolved (10/10 Round 5 fixes applied)
* **Date:** 2026-11-12

## Reviewer Status

| Reviewer | Status | Focus Lens |
| :--- | :--- | :--- |
| `egm-design` | **completed** | Ergonomics, CLI/MCP surface consistency, safety anti-patterns |
| `egm-structural` | **completed** | Pydantic models, DAG topologies, precedence rules, schema validity |
| `egm-implementation-readiness` | **completed** | FSM re-entrancy, REST/SSE protocols, timeouts, path traversal |
| `egm-codebase-details` | **completed** | `types.py`, `SessionManager`, `WorkspaceManager`, SQLite WAL, test plans |

---

## Severity Summary

* 🔴 **Blocker**: 0
* 🟡 **Major**: 5
* 🟢 **Nit**: 5
* **Total Prioritized Findings**: 10

---

## Prioritized Findings & AI Suggestions

### 1. Missing `model` Attribute in `TaskSpec` Specification [`egm-codebase-details`] - Severity: Major
* **Affected Scope:** [Lines 549–559](docs/designs/roles_teams_and_presets.md#L549-L559) (Section Detailed Implementation Plan - 1. Core Data Models)
* **Discrepancy Description:** `TaskSpec` in `harness_bridge/core/types.py` does not define a `model` attribute. When `DynamicRoleBinder` binds a role to an execution target `(harness, device_id, model)`, `SessionManager.execute_task(task)` cannot convey the resolved model to the harness drivers to pass `--model <model>` to CLI subprocesses.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Add `model: str | None = None` to `TaskSpec` in Section 5.1 and specify driver update in Section 5.10.

### 2. Undefined Remote Fleet Discovery Payload Contract [`egm-implementation-readiness`] - Severity: Major
* **Affected Scope:** [Lines 361–368, 468](docs/designs/roles_teams_and_presets.md#L361-L368) (Section Core Component Architecture - 3. Fleet Discovery, Section 4)
* **Discrepancy Description:** The specification introduces `harness-bridge fleet register <gateway_url>` and `bridge_register_target`, but does not define the discovery endpoint or JSON response schema returned by the remote gateway to provide `device_id`, supported `harnesses`, available `models`, and `capabilities`.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Define discovery response schema returned by Remote Gateway endpoint (`GET /health` or `GET /api/v1/info`).

### 3. Ambiguous `host_gateway_url` Resolution for Remote Workers [`egm-implementation-readiness` / `egm-design`] - Severity: Major
* **Affected Scope:** [Lines 367–375](docs/designs/roles_teams_and_presets.md#L367-L375) (Section Core Component Architecture - 3. Fleet Discovery)
* **Discrepancy Description:** If `host_gateway_url` defaults to `127.0.0.1` or `localhost`, remote workers on separate physical machines will fail when attempting to download artifacts or post completion.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Define resolution order for `host_gateway_url`: CLI option (`--gateway-url`) / env var (`HARNESS_BRIDGE_GATEWAY_URL`), falling back to detected non-loopback / Tailscale IP, with loopback validation guard.

### 4. Remote Prompt Absolute Path Incompatibility for `{scratch_dir}` and Upstream Artifacts [`egm-structural` / `egm-implementation-readiness`] - Severity: Major
* **Affected Scope:** [Lines 243–253, 370–375](docs/designs/roles_teams_and_presets.md#L243-L253) (Section 2, Section 3.3)
* **Discrepancy Description:** Host-local absolute paths for `{scratch_dir}` and `{steps.<step_id>.artifact_path}` do not exist on remote worker filesystems if interpolated prior to dispatch.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Specify that `POST /api/v1/dispatch` transmits the un-interpolated prompt template and context parameters so interpolation evaluates against the remote worker's local scratchpad workspace.

### 5. Missing Test Coverage for Remote Gateway RPC & Path Traversal Security [`egm-codebase-details` / `egm-implementation-readiness`] - Severity: Major
* **Affected Scope:** [Lines 648–655, 664–680](docs/designs/roles_teams_and_presets.md#L648-L655) (Section 5.13, Verification Plan)
* **Discrepancy Description:** Neither Section 5.13 nor the Verification Plan mentions tests for the Remote Gateway endpoints or path traversal rejection (`../../etc/passwd`).
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Add `tests/test_gateway_teams.py` to Section 5.13 and add remote dispatch and path traversal scenarios to Verification Plan.

### 6. Redundant Mandatory `decision` Parameter on `bridge_approve_gate` [`egm-design`] - Severity: Nit
* **Affected Scope:** [Lines 457–469](docs/designs/roles_teams_and_presets.md#L457-L469) (Section 4 MCP Tools)
* **Discrepancy Description:** `bridge_approve_gate` requires explicit `decision: Literal["approved", "rejected"]` when a separate `bridge_reject_gate` exists.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Set default `decision: Literal["approved", "rejected"] = "approved"`.

### 7. Signature Parameter Discrepancy in `TokenTelemetryStore.record` [`egm-codebase-details`] - Severity: Nit
* **Affected Scope:** [Lines 601–606](docs/designs/roles_teams_and_presets.md#L601-L606) (Section 5.7)
* **Discrepancy Description:** `record` signature omits `total_tokens`.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Update signature to accept `total_tokens: int` (or `token_usage: TokenUsage`).

### 8. Singular vs Collection Return Type on `get_role_model_benchmarks` [`egm-codebase-details` / `egm-structural`] - Severity: Nit
* **Affected Scope:** [Lines 601–606](docs/designs/roles_teams_and_presets.md#L601-L606) (Section 5.7)
* **Discrepancy Description:** `get_role_model_benchmarks` returns `HistoricalTokenAnalytics` scalar, but unfiltered queries return multiple records.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Update return type to `list[HistoricalTokenAnalytics]` when querying without specific role/model filters.

### 9. Ambiguity in `orchestrator_role` Validation vs Built-in Presets [`egm-structural`] - Severity: Nit
* **Affected Scope:** [Lines 199–206, 564–570](docs/designs/roles_teams_and_presets.md#L199-L206) (Section 2, Section 5.3)
* **Discrepancy Description:** `orchestrator_role: str = "orchestrator"` validation would fail for presets that don't define an `"orchestrator"` role in `roles`.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Clarify `orchestrator_role: str | None = None` and validate only if explicitly referenced or declared in `roles`.

### 10. Absence of a Complete Declarative YAML Preset Example [`egm-design` / `egm-structural`] - Severity: Nit
* **Affected Scope:** [Lines 138–150](docs/designs/roles_teams_and_presets.md#L138-L150) (Section 2)
* **Discrepancy Description:** Lacks a complete reference YAML preset snippet illustrating v0.3.0 schema features.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Add sample `feature-dev.yaml` snippet to Section 2.
