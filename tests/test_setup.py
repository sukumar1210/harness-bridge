import pytest

from harness_bridge.core.setup import (
    check_agy_configured_fast,
    check_claude_configured_fast,
    setup_all_harnesses,
)


@pytest.mark.asyncio
async def test_setup_all_harnesses():
    results = await setup_all_harnesses()
    assert isinstance(results, list)
    harnesses = [r.harness for r in results]
    assert "claude" in harnesses
    assert "agy" in harnesses
    for r in results:
        assert r.status in ("configured", "already_configured", "not_installed")


def test_fast_config_check():
    # Should not throw any exception regardless of local state
    res_claude = check_claude_configured_fast()
    assert isinstance(res_claude, bool)

    res_agy = check_agy_configured_fast()
    assert isinstance(res_agy, bool)
