import pytest

from harness_bridge.server.mcp_server import bridge_list_harnesses


@pytest.mark.asyncio
async def test_mcp_list_harnesses_tool():
    tools = await bridge_list_harnesses()
    assert isinstance(tools, list)
    names = [t["name"] for t in tools]
    assert "claude" in names
    assert "agy" in names
