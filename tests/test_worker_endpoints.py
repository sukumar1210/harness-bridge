from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from starlette.applications import Starlette

from harness_bridge.core.types import TaskRecord
from harness_bridge.relay.bus import RelayBus
from harness_bridge.relay.store import RelayStore
from harness_bridge.server.mcp_server import create_worker_routes


@pytest.fixture
def app_and_bus(tmp_path: Path):
    store = RelayStore(db_path=tmp_path / "test_api_relay.db")
    bus = RelayBus(store=store)
    routes = create_worker_routes(bus)
    app = Starlette(routes=routes)
    return app, bus


@pytest.mark.asyncio
async def test_worker_endpoints_auth(app_and_bus):
    """Verify HARNESS_BRIDGE_TOKEN authentication requirement."""
    app, bus = app_and_bus

    with patch.dict(os.environ, {"HARNESS_BRIDGE_TOKEN": "secret-token-123"}):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Unauthenticated request should be rejected with 401
            resp = await client.get("/api/v1/workers")
            assert resp.status_code == 401
            assert "Unauthorized" in resp.json()["error"]

            # Authenticated request with Bearer header should succeed
            auth_headers = {"Authorization": "Bearer secret-token-123"}
            resp_auth = await client.get("/api/v1/workers", headers=auth_headers)
            assert resp_auth.status_code == 200
            assert resp_auth.json() == []


@pytest.mark.asyncio
async def test_task_rest_lifecycle_endpoints(app_and_bus):
    """Verify /ack, /heartbeat, /complete, and /fail REST endpoints."""
    app, bus = app_and_bus
    await bus.start()

    # Pre-seed a task in pending status
    task = TaskRecord(
        task_id="tsk-test-1",
        session_id="sess-api-1",
        harness="claude",
        prompt="Test prompt",
    )
    bus.store.save_task(task)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Acknowledge task lease
        ack_resp = await client.post(
            "/api/v1/tasks/tsk-test-1/ack",
            json={"worker_id": "worker-xyz"},
        )
        assert ack_resp.status_code == 200
        assert ack_resp.json()["ok"] is True

        # Duplicate ACK should fail with 409
        ack_dup = await client.post(
            "/api/v1/tasks/tsk-test-1/ack",
            json={"worker_id": "worker-other"},
        )
        assert ack_dup.status_code == 409

        # 2. Heartbeat renewal
        hb_resp = await client.post(
            "/api/v1/tasks/tsk-test-1/heartbeat",
            json={"worker_id": "worker-xyz"},
        )
        assert hb_resp.status_code == 200
        assert hb_resp.json()["ok"] is True

        # 3. Complete task
        res_payload = {
            "session_id": "sess-api-1",
            "harness": "claude",
            "status": "completed",
            "output": "All tests passed cleanly",
            "exit_code": 0,
        }
        comp_resp = await client.post(
            "/api/v1/tasks/tsk-test-1/complete",
            json={"worker_id": "worker-xyz", "result": res_payload},
        )
        assert comp_resp.status_code == 200
        assert comp_resp.json()["ok"] is True

        # Verify task state in database
        updated_task = bus.store.get_task("tsk-test-1")
        assert updated_task.status == "completed"
        assert updated_task.result.output == "All tests passed cleanly"

    await bus.stop()


@pytest.mark.asyncio
async def test_task_fail_endpoint(app_and_bus):
    """Verify /fail endpoint records failure status and error details."""
    app, bus = app_and_bus
    await bus.start()

    task = TaskRecord(
        task_id="tsk-fail-1",
        session_id="sess-api-2",
        harness="agy",
        prompt="Fail prompt",
    )
    bus.store.save_task(task)
    bus.ack_task("tsk-fail-1", "worker-xyz")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        fail_resp = await client.post(
            "/api/v1/tasks/tsk-fail-1/fail",
            json={"worker_id": "worker-xyz", "error": "Disk out of space", "exit_code": 1},
        )
        assert fail_resp.status_code == 200
        assert fail_resp.json()["ok"] is True

        updated = bus.store.get_task("tsk-fail-1")
        assert updated.status == "failed"
        assert updated.error == "Disk out of space"

    await bus.stop()


def test_cli_worker_help():
    """Verify worker CLI subcommand help and option parsing."""
    import re

    from typer.testing import CliRunner

    from harness_bridge.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["worker", "--help"])
    assert result.exit_code == 0
    clean_stdout = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.stdout)
    assert "--server" in clean_stdout
    assert "--token" in clean_stdout
    assert "--harness" in clean_stdout
    assert "--worker-id" in clean_stdout
