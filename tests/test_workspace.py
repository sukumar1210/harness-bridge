import pytest
from pathlib import Path
from harness_bridge.workspace.manager import WorkspaceManager


@pytest.mark.asyncio
async def test_workspace_inherit_mode(temp_git_repo):
    mgr = WorkspaceManager()
    ws = await mgr.prepare_workspace(mode="inherit", repo_root=temp_git_repo, session_id="test-session-1")
    assert ws == temp_git_repo


@pytest.mark.asyncio
async def test_workspace_worktree_isolation_and_diff(temp_git_repo):
    mgr = WorkspaceManager()
    session_id = "test-session-worktree"

    # 1. Prepare worktree
    ws = await mgr.prepare_workspace(mode="worktree", repo_root=temp_git_repo, session_id=session_id)
    assert ws.exists()
    assert (temp_git_repo / ".worktrees" / session_id) == ws

    # 2. Modify files and add a new untracked file in worktree
    (ws / "new_module.py").write_text("print('hello world')\n", encoding="utf-8")
    (ws / "README.md").write_text("# Test Repository Modified\n", encoding="utf-8")

    # 3. Extract diff
    diff = await mgr.extract_diff(ws)
    assert "new_module.py" in diff
    assert "Test Repository Modified" in diff

    # Verify main repo is pristine
    main_readme = (temp_git_repo / "README.md").read_text(encoding="utf-8")
    assert main_readme == "# Test Repository\n"
    assert not (temp_git_repo / "new_module.py").exists()

    # 4. Apply diff
    apply_res = await mgr.apply_diff(repo_root=temp_git_repo, session_id=session_id)
    assert apply_res.success is True
    assert (temp_git_repo / "new_module.py").exists()

    # 5. Cleanup
    await mgr.cleanup_workspace(session_id=session_id, worktree_path=ws, repo_root=temp_git_repo, delete_branch=True)
    assert not ws.exists()
