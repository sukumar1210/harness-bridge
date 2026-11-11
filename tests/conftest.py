import os
import shutil
import tempfile
from pathlib import Path
import pytest
from harness_bridge.core.process import run_command_safe


@pytest.fixture
def temp_git_repo():
    """Create a temporary initialized git repository with an initial commit."""
    tmp_dir = tempfile.mkdtemp(prefix="hb_test_repo_")
    repo_path = Path(tmp_dir).resolve()

    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True)

    test_file = repo_path / "README.md"
    test_file.write_text("# Test Repository\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)

    yield repo_path

    shutil.rmtree(repo_path, ignore_errors=True)
