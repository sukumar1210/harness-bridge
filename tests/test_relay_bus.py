from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from harness_bridge.core.types import TaskRecord, TaskResult, TaskSpec, WorkerInfo
from harness_bridge.relay.bus import RelayBus
from harness_bridge.relay.embedded import EmbeddedWorker
from harness_bridge.relay.store import RelayStore


@pytest.fixture
def temp_store(tmp_path: Path) -> RelayStore:
    db_file = tmp_path / "test_relay.db"
    return RelayStore(db_path=db_file)


@pytest.fixture
def relay_bus(temp_store: RelayStore) -> RelayBus:
    return RelayBus(store=temp_store)


def test_relay_store_crud(temp_store: RelayStore):
    """Test basic task persistence, updates, and querying."""
    task = TaskRecord(
        task_id="t-1",
        session_id="s-1",
        harness="claude",
        prompt="hello world",
        workspace_mode="inherit",
        timeout_seconds=60,
    )
    temp_store.save_task(task)

    loaded = temp_store.get_task("t-1")
    assert loaded is not None
    assert loaded.task_id == "t-1"
    assert loaded.session_id == "s-1"
    assert loaded.status == "pending"

    # Claim task
    claimed = temp_store.claim_task("t-1", "worker-1", lease_seconds=30.0)
    assert claimed is True

    # Duplicate claim should fail
    claimed_again = temp_store.claim_task("t-1", "worker-2", lease_seconds=30.0)
    assert claimed_again is False

    # Renew lease
    renewed = temp_store.renew_lease("t-1", "worker-1", lease_seconds=60.0)
    assert renewed is True

    # Renew by wrong worker should fail
    renew_wrong = temp_store.renew_lease("t-1", "worker-2")
    assert renew_wrong is False

    # Complete task
    result = TaskResult(
        session_id="s-1",
        harness="claude",
        status="completed",
        output="Done!",
        exit_code=0,
    )
    completed = temp_store.complete_task("t-1", "worker-1", result)
    assert completed is True

    task_done = temp_store.get_task("t-1")
    assert task_done.status == "completed"
    assert task_done.result is not None
    assert task_done.result.output == "Done!"


def test_relay_store_worker_presence_and_affinity(temp_store: RelayStore):
    """Test worker registration, liveness heartbeat, and sticky session affinity."""
    worker = WorkerInfo(
        worker_id="w-alpha",
        harnesses=["agy", "claude"],
        device_name="workstation-1",
    )
    temp_store.register_worker(worker)

    active = temp_store.list_active_workers()
    assert len(active) == 1
    assert active[0].worker_id == "w-alpha"
    assert "agy" in active[0].harnesses

    # Filter by harness
    assert len(temp_store.list_active_workers(harness="agy")) == 1
    assert len(temp_store.list_active_workers(harness="nonexistent")) == 0

    # Session affinity
    temp_store.set_session_affinity("sess-100", "w-alpha")
    assert temp_store.get_session_affinity("sess-100") == "w-alpha"
    assert temp_store.get_session_affinity("sess-unknown") is None

    # Deactivate worker
    temp_store.deactivate_worker("w-alpha")
    assert len(temp_store.list_active_workers()) == 0


def test_relay_store_lease_expiration(temp_store: RelayStore):
    """Test watchdog lease expiration cleanup."""
    task = TaskRecord(
        task_id="t-expire",
        session_id="s-exp",
        harness="agy",
        prompt="expire me",
    )
    temp_store.save_task(task)
    # Claim with negative lease so it is already expired
    temp_store.claim_task("t-expire", "w-1", lease_seconds=-5.0)

    # Clean with 0 grace period
    expired = temp_store.clean_expired_leases(grace_period_seconds=0.0)
    assert "t-expire" in expired

    loaded = temp_store.get_task("t-expire")
    assert loaded.status == "timeout"


@pytest.mark.asyncio
async def test_relay_bus_lifecycle_and_dispatch(relay_bus: RelayBus):
    """Test full dispatch lifecycle: worker subscribes, receives task offer, acks, and completes."""
    await relay_bus.start()

    received_events = []

    async def run_worker():
        async for ev in relay_bus.subscribe_worker("w-test", ["claude"]):
            received_events.append(ev)
            if ev.get("event") == "task_offer":
                task_id = ev["task_id"]
                # Acknowledge
                relay_bus.ack_task(task_id, "w-test")
                # Send heartbeat
                relay_bus.heartbeat_task(task_id, "w-test")
                # Complete
                res = TaskResult(
                    session_id=ev["session_id"],
                    harness="claude",
                    status="completed",
                    output="Turn output executed",
                    exit_code=0,
                )
                relay_bus.complete_task(task_id, "w-test", res)
                break

    worker_task = asyncio.create_task(run_worker())
    await asyncio.sleep(0.05)  # Allow worker to subscribe

    spec = TaskSpec(
        harness="claude",
        prompt="Write a function",
        session_id="sess-bus-1",
        timeout_seconds=10,
    )
    task_rec = await relay_bus.submit_task(spec)
    result = await relay_bus.wait_for_task_completion(task_rec.task_id, timeout=5.0)

    assert result.status == "completed"
    assert result.output == "Turn output executed"
    assert len(received_events) > 0
    assert received_events[0]["event"] == "task_offer"

    await worker_task
    await relay_bus.stop()


@pytest.mark.asyncio
async def test_relay_bus_session_affinity_routing(relay_bus: RelayBus):
    """Test that consecutive turns for the same session route strictly to the affinity worker."""
    await relay_bus.start()

    # Pre-set session affinity to worker-alpha
    relay_bus.store.set_session_affinity("session-sticky", "worker-alpha")

    alpha_events = []
    beta_events = []

    async def worker_alpha():
        async for ev in relay_bus.subscribe_worker("worker-alpha", ["agy"]):
            if ev.get("event") == "task_offer":
                alpha_events.append(ev)
                relay_bus.ack_task(ev["task_id"], "worker-alpha")
                relay_bus.complete_task(
                    ev["task_id"],
                    "worker-alpha",
                    TaskResult(
                        session_id="session-sticky",
                        harness="agy",
                        status="completed",
                        output="Alpha ok",
                    ),
                )
                break

    async def worker_beta():
        async for ev in relay_bus.subscribe_worker("worker-beta", ["agy"]):
            if ev.get("event") == "task_offer":
                beta_events.append(ev)
                break

    t_alpha = asyncio.create_task(worker_alpha())
    t_beta = asyncio.create_task(worker_beta())
    await asyncio.sleep(0.05)

    spec = TaskSpec(
        harness="agy",
        prompt="Turn 2 follow-up",
        session_id="session-sticky",
        timeout_seconds=5,
    )
    task = await relay_bus.submit_task(spec)
    res = await relay_bus.wait_for_task_completion(task.task_id, timeout=5.0)

    assert res.status == "completed"
    assert res.output == "Alpha ok"
    assert len(alpha_events) == 1
    assert len(beta_events) == 0  # Beta was skipped because of affinity

    await t_alpha
    t_beta.cancel()
    try:
        await t_beta
    except asyncio.CancelledError:
        pass
    await relay_bus.stop()


@pytest.mark.asyncio
async def test_embedded_worker_execution(relay_bus: RelayBus):
    """Verify in-process EmbeddedWorker claims tasks and calls session_manager."""
    await relay_bus.start()

    mock_session_mgr = AsyncMock()
    mock_session_mgr.execute_task.return_value = TaskResult(
        session_id="sess-emb-1",
        harness="agy",
        status="completed",
        output="Embedded success",
    )

    worker = EmbeddedWorker(
        relay_bus=relay_bus,
        session_manager=mock_session_mgr,
        worker_id="embedded-test-1",
        harnesses=["agy"],
    )
    await worker.start()
    await asyncio.sleep(0.05)

    spec = TaskSpec(
        harness="agy",
        prompt="Run test in embedded worker",
        session_id="sess-emb-1",
        timeout_seconds=5,
    )
    task = await relay_bus.submit_task(spec)
    res = await relay_bus.wait_for_task_completion(task.task_id, timeout=5.0)

    assert res.status == "completed"
    assert res.output == "Embedded success"
    assert mock_session_mgr.execute_task.called

    await worker.stop()
    await relay_bus.stop()
