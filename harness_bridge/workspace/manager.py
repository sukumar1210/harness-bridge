from __future__ import annotations

import shutil
from pathlib import Path

from harness_bridge.core.exceptions import WorkspaceError
from harness_bridge.core.process import run_command_safe
from harness_bridge.core.types import ApplyResult, WorkspaceMode


class WorkspaceManager:
    """Manages workspace lifecycle including ephemeral git worktrees and diff application."""

    async def prepare_workspace(
        self,
        mode: WorkspaceMode,
        repo_root: Path,
        session_id: str,
    ) -> Path:
        """Prepare an isolated or shared workspace for task execution."""
        repo_root = repo_root.resolve()

        if mode == "inherit":
            return repo_root

        # Mode is 'worktree': ensure git repo
        git_dir = repo_root / ".git"
        if not git_dir.exists():
            raise WorkspaceError(f"Directory is not a git repository: {repo_root}")

        # Clean up stale worktrees first
        await run_command_safe(["git", "worktree", "prune", "--expire", "now"], cwd=repo_root)

        worktrees_dir = repo_root / ".worktrees"
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        worktree_path = (worktrees_dir / session_id).resolve()
        branch_name = f"bridge/session-{session_id}"

        # If previous worktree or directory exists, clean it up
        if worktree_path.exists():
            await run_command_safe(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=repo_root)
            if worktree_path.exists():
                shutil.rmtree(worktree_path, ignore_errors=True)

        # Remove pre-existing branch if any
        await run_command_safe(["git", "branch", "-D", branch_name], cwd=repo_root)

        # Add worktree linked to a new branch from HEAD
        code, stdout, stderr = await run_command_safe(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), "HEAD"],
            cwd=repo_root,
        )
        if code != 0:
            raise WorkspaceError(f"Failed to create git worktree:\n{stderr or stdout}")

        return worktree_path

    async def extract_diff(self, worktree_path: Path, base_ref: str = "HEAD") -> str:
        """Extract unified git diff including untracked files."""
        worktree_path = worktree_path.resolve()
        # Stage untracked files intent-to-add so they appear in diff
        await run_command_safe(["git", "add", "-N", "."], cwd=worktree_path)

        code, stdout, stderr = await run_command_safe(["git", "diff", base_ref], cwd=worktree_path)
        if code != 0:
            return ""
        return stdout

    async def apply_diff(self, repo_root: Path, session_id: str) -> ApplyResult:
        """Merge or apply changes produced in the session worktree branch into repo_root."""
        repo_root = repo_root.resolve()
        branch_name = f"bridge/session-{session_id}"
        worktree_path = (repo_root / ".worktrees" / session_id).resolve()

        # If worktree is still active, stage and commit any uncommitted changes into the branch
        if worktree_path.exists():
            await run_command_safe(["git", "add", "-A"], cwd=worktree_path)
            _, status_out, _ = await run_command_safe(
                ["git", "status", "--porcelain"],
                cwd=worktree_path,
            )
            if status_out.strip():
                await run_command_safe(
                    ["git", "commit", "-m", f"chore: session changes for {session_id}"],
                    cwd=worktree_path,
                )

        # Verify branch exists
        code, stdout, stderr = await run_command_safe(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=repo_root,
        )
        if code != 0:
            return ApplyResult(
                session_id=session_id,
                success=False,
                message=f"Branch {branch_name} not found.",
                applied_files=[],
            )

        # Identify files changed in the branch compared to HEAD
        code, diff_names, _ = await run_command_safe(
            ["git", "diff", "--name-only", "HEAD", branch_name],
            cwd=repo_root,
        )
        changed_files = [f.strip() for f in diff_names.splitlines() if f.strip()]

        # Generate patch and check if changes exist
        code, patch, stderr = await run_command_safe(
            ["git", "diff", "HEAD", branch_name],
            cwd=repo_root,
        )
        if code != 0 or not patch.strip():
            return ApplyResult(
                session_id=session_id,
                success=True,
                message="No changes to apply.",
                applied_files=[],
            )

        # Checkout branch changes into the repository working copy
        merge_code, m_out, m_err = await run_command_safe(
            ["git", "checkout", branch_name, "--", "."],
            cwd=repo_root,
        )
        if merge_code != 0:
            return ApplyResult(
                session_id=session_id,
                success=False,
                message=f"Failed to apply changes from {branch_name}:\n{m_err or m_out}",
                applied_files=[],
            )

        return ApplyResult(
            session_id=session_id,
            success=True,
            message=f"Successfully applied changes from {branch_name}.",
            applied_files=changed_files,
        )

    async def cleanup_workspace(
        self,
        session_id: str,
        worktree_path: Path,
        repo_root: Path,
        delete_branch: bool = False,
    ) -> None:
        """Safely remove ephemeral worktree. Strict no-op if worktree is the main repository root."""
        worktree_path = worktree_path.resolve()
        repo_root = repo_root.resolve()

        if worktree_path == repo_root:
            return

        await run_command_safe(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
        )
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        if delete_branch:
            branch_name = f"bridge/session-{session_id}"
            await run_command_safe(["git", "branch", "-D", branch_name], cwd=repo_root)

        await run_command_safe(["git", "worktree", "prune", "--expire", "now"], cwd=repo_root)
