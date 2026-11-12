# Workspace Manager (`harness_bridge.workspace`)

## Overview
The `harness_bridge.workspace` package provides isolated workspace lifecycle management for AI coding harnesses. It orchestrates ephemeral git worktrees and diff application, enabling child agent harnesses to execute coding tasks in sandboxed directories without interfering with the parent repository's working tree or concurrent operations.

## Interface
- `WorkspaceManager`: Central manager class orchestrating workspace lifecycles, git worktree provisioning, diff extraction, and repository patch application.
  - `prepare_workspace(mode: WorkspaceMode, repo_root: Path, session_id: str) -> Path`: Prepares an execution workspace. In `"inherit"` mode, resolves and returns `repo_root`. In `"worktree"` mode, verifies the git repository, prunes stale worktrees, cleans up prior sessions, and creates an isolated git worktree at `.worktrees/{session_id}` attached to branch `bridge/session-{session_id}`.
  - `extract_diff(worktree_path: Path, base_ref: str = "HEAD") -> str`: Extracts unified git diffs between `base_ref` and current state in `worktree_path`, automatically staging untracked files (`git add -N .`) so newly created files are included.
  - `apply_diff(repo_root: Path, session_id: str) -> ApplyResult`: Merges or applies changes from `bridge/session-{session_id}` into `repo_root`. Automatically commits uncommitted worktree changes, applies deletions, and checks out changed files into the primary repository tree.
  - `cleanup_workspace(session_id: str, worktree_path: Path, repo_root: Path, delete_branch: bool = False) -> None`: Safely tears down ephemeral worktrees and prunes git metadata. Includes a strict no-op guard when `worktree_path == repo_root` to prevent accidental deletion in `"inherit"` mode.

## Invariants
- **Git Worktree Isolation**: Under `"worktree"` mode, all modifications and intermediate files remain isolated in `.worktrees/{session_id}` until explicitly applied, keeping the main repository clean.
- **Deterministic Branch Naming**: Branches dedicated to session workspaces strictly follow the pattern `bridge/session-{session_id}`, preventing naming collisions across independent sessions.
- **Directory & Re-entrance Collision Prevention**: Stale worktree directories and branches for the same session ID are forcefully removed and pruned prior to provisioning a new workspace.
- **Repository Deletion Safety**: `cleanup_workspace` immediately returns without deleting when `worktree_path == repo_root`, ensuring `"inherit"` mode workspaces cannot delete the base repository.
- **Diff Completeness**: Untracked files are staged intent-to-add (`git add -N .`) prior to computing diffs, and uncommitted modifications are committed before applying diffs into the target repository.

## Side Effects
- **Git Worktree & Branch Mutation**: Invokes git commands (`git worktree add`, `git worktree remove`, `git branch -D`, `git worktree prune`) that modify `.git` metadata and create/delete local branches.
- **File System Alterations**: Creates `.worktrees/{session_id}` directories on disk, creates temporary commits with author `"Harness Bridge <bridge@internal>"`, and removes deleted files or directories from `repo_root` during `apply_diff`.
- **Target Working Copy Updates**: Directly updates files in `repo_root` during `apply_diff` using `git checkout bridge/session-{session_id} -- .`.

## Verification
- Run: `pytest tests/test_workspace.py`
