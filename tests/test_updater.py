import pytest
from harness_bridge.core.updater import parse_semver


def test_parse_semver():
    assert parse_semver("v0.1.0") == (0, 1, 0)
    assert parse_semver("0.2.1") == (0, 2, 1)
    assert parse_semver("v1.0.0-rc1") == (1, 0, 0)
    assert parse_semver("0.1.0") < parse_semver("0.2.0")
    assert parse_semver("1.0.0") > parse_semver("0.9.9")
