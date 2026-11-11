import pytest
from harness_bridge.core.exceptions import MaxHopsExceededError
from harness_bridge.core.types import TaskSpec
from harness_bridge.session.manager import SessionManager


@pytest.mark.asyncio
async def test_session_manager_hop_limit():
    mgr = SessionManager()
    spec = TaskSpec(
        harness="agy",
        prompt="echo test",
        hop_count=10,
        max_hops=10,
    )
    with pytest.raises(MaxHopsExceededError):
        await mgr.execute_task(spec)
