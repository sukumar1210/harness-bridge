from harness_bridge.drivers.antigravity import AntigravityDriver
from harness_bridge.drivers.claude import ClaudeCodeDriver
from harness_bridge.drivers.registry import get_driver, list_all_harness_info


def test_driver_registry():
    claude = get_driver("claude")
    assert isinstance(claude, ClaudeCodeDriver)
    assert claude.name == "claude"

    agy = get_driver("agy")
    assert isinstance(agy, AntigravityDriver)
    assert agy.name == "agy"

    antigravity_alias = get_driver("antigravity")
    assert antigravity_alias.name == "agy"


def test_list_harness_info():
    infos = list_all_harness_info()
    names = [i.name for i in infos]
    assert "claude" in names
    assert "agy" in names
