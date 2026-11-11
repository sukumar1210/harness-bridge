# Goldfish Annotated Review Report

* **Target:** `docs/designs/roles_teams_and_presets.md` (`Lines 1-496`)
* **Status:** Resolved (15/15 fixes applied)
* **Date:** 2026-11-12

## Reviewer Status

| Reviewer | Status |
| :--- | :--- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |

## Severity Summary

* 🔴 **Blocker**: 3
* 🟡 **Major**: 7
* 🟢 **Nit**: 5
* **Total Prioritized Findings**: 15

---

## Prioritized Findings & AI Suggestions

### 1. Preflight HTTP/TCP Probes vs. Daemonless Remote Nodes [`egm-implementation-readiness` / `egm-codebase-details`] - Severity: Blocker
* **Affected Scope:** [Lines 243-249, 330-335, 401-406](docs/designs/roles_teams_and_presets.md#L243-L249) (Section 3.3, Alternatives #3, Section 5.5)
* **Discrepancy Description:** The design rejects standing background daemons in Alternatives Considered #3 to avoid resource overhead. However, Section 3.3 specifies that dynamic role binding dispatches an opportunistic just-in-time HTTP/TCP health probe (<1.5s) to remote hosts before stage execution. If remote nodes run no background service, there is no listening socket to receive TCP/HTTP probes.
* **Rationale:** A probe cannot connect to a host that exposes no listening endpoint.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Clarify that remote machines run the authenticated Remote Gateway daemon (from v0.2.0 `docs/designs/aggregated_sessions_and_remote_gateway.md`) which exposes health/SSE endpoints, whereas the "no daemon" alternative specifically meant avoiding a *continuous 30s broadcast heartbeat process*.
* **Proposed Edit:**
  * Location: Section 3.3 & Section 4 (Alternative 3)
  * Change: Explicitly distinguish between standing continuous heartbeat broadcasters (rejected) vs. standard on-demand Remote Gateway endpoints (v0.2.0) queried via preflight probe.

---

### 2. `WorkspaceMode` Type Conflict & Fatal Crash in Non-Git Repositories (CUJ 2) [`egm-codebase-details` / `egm-design`] - Severity: Blocker
* **Affected Scope:** [Lines 150, 57-60, 431-436](docs/designs/roles_teams_and_presets.md#L150) (Section 2, CUJ 2, Section 5.9)
* **Discrepancy Description:** `RoleDefinition` introduces `workspace_mode: Literal["worktree", "scratch", "inherit"] = "scratch"`, whereas `harness_bridge/core/types.py` defines `WorkspaceMode = Literal["inherit", "worktree"]`. Additionally, `WorkspaceManager.prepare_workspace()` asserts `.git` directory existence for non-inherit modes. Running `"scratch"` in an empty non-git directory (CUJ 2) triggers a fatal `WorkspaceError`.
* **Rationale:** CUJ 2 cannot execute without native non-git scratchpad support in `WorkspaceManager`.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Add `"scratch"` to `WorkspaceMode` in `types.py` and update `prepare_workspace()` to handle `"scratch"` without asserting `.git` existence.
* **Proposed Edit:**
  * Location: Section 5.1 & Section 5.9
  * Change: Update `WorkspaceMode` enum and document non-git scratchpad initialization in `WorkspaceManager`.

---

### 3. Indeterminate Execution Model: Synchronous vs. Asynchronous MCP Tool Dispatch [`egm-implementation-readiness` / `egm-structural`] - Severity: Blocker
* **Affected Scope:** [Lines 186-195, 298-299, 408-414](docs/designs/roles_teams_and_presets.md#L186-L195) (Section 3.1, Section 4, Section 5.6)
* **Discrepancy Description:** The specification does not define whether `bridge_run_team` is synchronous or asynchronous. Multi-agent workflows with human approval gates pause for hours. If synchronous, stdio client timeouts terminate parent sessions.
* **Rationale:** LLM CLI harnesses enforce 60-300s stdio timeouts; team swarms cannot block the tool call.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Formally specify `bridge_run_team` as asynchronous: returns immediately with `run_id`, starting background FSM execution. Calling session checks progress via `bridge_get_team_status` or Remote Gateway SSE.
* **Proposed Edit:**
  * Location: Section 3.1 & Section 4 (Tool table)
  * Change: Document asynchronous job dispatch semantics and status polling lifecycle.

---

### 4. Unsafe Default Auto-Proceed in `GatePolicy` & Missing Schema Validator [`egm-design`] - Severity: Major
* **Affected Scope:** [Lines 152-156, 251-257, 318-323](docs/designs/roles_teams_and_presets.md#L152-L156) (Section 2, Section 3.4, Alternative 1)
* **Discrepancy Description:** `GatePolicy` schema sets `timeout_action = "proceed"` and `timeout_seconds = 120` by default. If a preset author marks `risk_level: "critical"` but omits `timeout_action`, mutating stages can auto-proceed unattended.
* **Rationale:** Contradicts the risk-tiered safety principle established in Alternative 1.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Change default `timeout_action` to `"pause"`. Add Pydantic `@model_validator(mode="after")` raising a validation error if `risk_level == "critical"` and `timeout_action == "proceed"`.
* **Proposed Edit:**
  * Location: Section 2 (`GatePolicy` model)
  * Change: Default `timeout_action = "pause"` and add Pydantic validator rejecting critical auto-proceed configurations.

---

### 5. Undefined Gate Rejection Semantics & FSM Transitions [`egm-design` / `egm-structural`] - Severity: Major
* **Affected Scope:** [Lines 253-257, 300, 311](docs/designs/roles_teams_and_presets.md#L253-L257) (Section 3.4, Section 4)
* **Discrepancy Description:** Endpoints allow rejecting a gate (`bridge_approve_gate(decision="rejected")`), but the FSM transition on rejection is undefined (halt vs rollback vs paused).
* **Rationale:** State engine cannot deterministically handle rejection without a declared state transition.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Formally define FSM rejection lifecycle: transitions to `rejected`, sets run status to `paused`, and supports an optional `on_reject: StepId` parameter to route back with feedback.
* **Proposed Edit:**
  * Location: Section 2 (`GatePolicy`) & Section 3.4
  * Change: Add `on_reject: str | None = None` and document rejection FSM state transitions.

---

### 6. Missing Artifact Parameterization & Variable Interpolation Protocol [`egm-structural` / `egm-implementation-readiness`] - Severity: Major
* **Affected Scope:** [Lines 158-165, 172](docs/designs/roles_teams_and_presets.md#L158-L165) (Section 2)
* **Discrepancy Description:** `WorkflowStep` defines `prompt_template: str` and `artifact_output: str | None`, but does not specify template context variables for referencing upstream deliverables.
* **Rationale:** Implementers need exact template variable contracts to connect multi-step DAG inputs and outputs.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Specify `str.format_map` interpolation supporting `{goal}`, `{run_id}`, `{scratch_dir}`, `{step_id}`, and `{steps.<id>.artifact_path}` / `{steps.<id>.output}`.
* **Proposed Edit:**
  * Location: Section 2 (`WorkflowStep`)
  * Change: Add template variable specification table and resolution semantics.

---

### 7. Missing DDL Specification for `device_leases` & Missing Foreign Key Indexes [`egm-implementation-readiness`] - Severity: Major
* **Affected Scope:** [Lines 199-241, 244-245](docs/designs/roles_teams_and_presets.md#L199-L241) (Section 3.2, Section 3.3)
* **Discrepancy Description:** Section 3.2 omits the `CREATE TABLE device_leases` DDL and lacks foreign key indexes on `run_id` across child tables.
* **Rationale:** Missing table causes migration failure; unindexed foreign keys degrade query performance at scale.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Provide complete DDL for `device_leases` and add indexes for `run_id` on `step_runs`, `gate_approvals`, and `token_telemetry`.
* **Proposed Edit:**
  * Location: Section 3.2 (SQLite Schema)
  * Change: Add `device_leases` DDL and foreign key indexes.

---

### 8. Git Worktree `.git` File vs. Directory Exclusion Hazard [`egm-codebase-details`] - Severity: Major
* **Affected Scope:** [Lines 258-261, 431-436](docs/designs/roles_teams_and_presets.md#L258-L261) (Section 3.5, Section 5.9)
* **Discrepancy Description:** In git worktrees (`.worktrees/<session_id>/`), `.git` is a pointer file, not a directory. Naive `repo_root / ".git" / "info" / "exclude"` will fail with `NotADirectoryError`.
* **Rationale:** Breaks scratchpad isolation inside git worktrees.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Resolve the exclude path dynamically using `git rev-parse --git-path info/exclude`.
* **Proposed Edit:**
  * Location: Section 3.5 & Section 5.9
  * Change: Replace hardcoded `.git/info/exclude` path with dynamic `git rev-parse --git-path info/exclude` resolution.

---

### 9. Ambiguous Orchestrator Role Resolution in Headless/CLI Invocation [`egm-design` / `egm-structural`] - Severity: Major
* **Affected Scope:** [Lines 185-195, 307-308, 56-60](docs/designs/roles_teams_and_presets.md#L185-L195) (Section 3.1, Section 4, CUJ 2)
* **Discrepancy Description:** When run from terminal (`harness-bridge team run`), there is no ambient calling LLM session to adopt the orchestrator role.
* **Rationale:** Clarifies whether CLI mode requires an LLM orchestrator turn or runs purely deterministically.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Clarify that CLI invocation runs standalone: the state engine evaluates the DAG directly without requiring an LLM orchestrator turn unless explicitly declared as a workflow step.
* **Proposed Edit:**
  * Location: Section 3.1 & Section 4
  * Change: Document dual orchestration modes: Calling-Session Mode (MCP) vs. Standalone Engine Mode (CLI).

---

### 10. Token Accounting Missing Structured Model & Zero-Division Guard [`egm-codebase-details` / `egm-structural`] - Severity: Major
* **Affected Scope:** [Lines 283-288, 379, 416-421](docs/designs/roles_teams_and_presets.md#L283-L288) (Section 3.6, Section 5.1, Section 5.7)
* **Discrepancy Description:** `TaskResult.token_usage` is an untyped dictionary, and percentage calculations risk `ZeroDivisionError` when `total_run_tokens == 0`.
* **Rationale:** Ensures type safety and runtime stability during initial/zero-token turns.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Define `TokenUsage` Pydantic model in `types.py` and guard percentage formulas with `total_run_tokens > 0`.
* **Proposed Edit:**
  * Location: Section 3.6 & Section 5.1
  * Change: Add `TokenUsage` class and zero-safe percentage formula.

---

### 11. CLI Flag Inconsistency: Positional `<goal>` vs. `--prompt` Option [`egm-design`] - Severity: Nit
* **Affected Scope:** [Lines 58, 307](docs/designs/roles_teams_and_presets.md#L58) (CUJ 2 vs Section 4)
* **Discrepancy Description:** Command table shows `<preset> <goal>` while CUJ 2 shows `--prompt "..."`.
* **Rationale:** Prevents developer confusion on CLI invocation syntax.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Support `harness-bridge team run <preset> [goal]` with `--prompt / -p` as an alias.
* **Proposed Edit:**
  * Location: Section 4 (CLI table)
  * Change: Document `[goal]` and `--prompt / -p` options.

---

### 12. Status Casing Discrepancy Across Codebase and Schemas [`egm-codebase-details` / `egm-structural`] - Severity: Nit
* **Affected Scope:** [Lines 203, 221, 236](docs/designs/roles_teams_and_presets.md#L203) (Section 3.2)
* **Discrepancy Description:** SQLite tables use uppercase (`RUNNING`, `COMPLETED`), while codebase uses lowercase literals (`"running"`).
* **Rationale:** Prevents string mismatch bugs and adheres to codebase convention.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Normalize all statuses to lowercase literals across SQL and Pydantic schemas.
* **Proposed Edit:**
  * Location: Section 3.2 (SQLite Schema)
  * Change: Lowercase all status values.

---

### 13. Missing Gate Feedback Column in `gate_approvals` Table [`egm-implementation-readiness`] - Severity: Nit
* **Affected Scope:** [Lines 228-240, 300](docs/designs/roles_teams_and_presets.md#L228-L240) (Section 3.2, Section 4)
* **Discrepancy Description:** `bridge_approve_gate` passes `feedback: str`, but table `gate_approvals` lacks a `feedback` column.
* **Rationale:** Feedback text provided during approval/rejection must be persisted.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Add `feedback TEXT` to `gate_approvals` table.
* **Proposed Edit:**
  * Location: Section 3.2 (SQLite Schema)
  * Change: Add `feedback TEXT` column.

---

### 14. Pydantic Type Annotation Syntax in `bridge_get_token_analytics` [`egm-codebase-details`] - Severity: Nit
* **Affected Scope:** [Line 301](docs/designs/roles_teams_and_presets.md#L301) (Section 4)
* **Discrepancy Description:** Tool signature uses `role: str = None` instead of PEP 484 `role: str | None = None`.
* **Rationale:** Conforms with Python 3.10+ typing standards.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Update parameter typing to `str | None = None`.
* **Proposed Edit:**
  * Location: Section 4 (MCP table)
  * Change: Update typing signatures.

---

### 15. Unspecified Parallel Step Execution Semantics in DAG Engine [`egm-implementation-readiness`] - Severity: Nit
* **Affected Scope:** [Lines 88, 162, 410-412](docs/designs/roles_teams_and_presets.md#L88) (Section 3, Section 5.6)
* **Discrepancy Description:** Spec does not clarify whether independent steps in DAG run concurrently via `asyncio.gather`.
* **Rationale:** Clarifies execution concurrency for fan-out presets.
* **AI Suggestion:** PROPOSE FIX
* **Justification:** Explicitly state that independent ready steps run concurrently via `asyncio.gather`.
* **Proposed Edit:**
  * Location: Section 3.1 & Section 5.6
  * Change: Document `asyncio.gather` concurrent execution of ready steps.
