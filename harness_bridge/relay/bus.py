from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator

from harness_bridge.core.exceptions import WorkerTimeoutError
from harness_bridge.core.types import (
    TaskRecord,
    TaskResult,
    TaskSpec,
    WorkerInfo,
)
from harness_bridge.relay.store import RelayStore

logger = logging.getLogger("harness-bridge.relay.bus")


class RelayBus:
    """In-memory event bus and task coordinator backed by durable SQLite RelayStore."""

    def __init__(self, store: RelayStore | None = None) -> None:
        self.store = store or RelayStore()
        # worker_id -> asyncio.Queue of event dicts
        self._worker_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        # worker_id -> WorkerInfo
        self._active_workers: dict[str, WorkerInfo] = {}
        # task_id -> asyncio.Event signaled when terminal state reached
        self._task_events: dict[str, asyncio.Event] = {}
        self._watchdog_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start background watchdog for lease timeouts."""
        if self._running:
            return
        self._running = True
        self._watchdog_task = asyncio.create_task(self._lease_watchdog_loop())

    async def stop(self) -> None:
        """Stop background watchdog."""
        self._running = False
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

    def _get_task_event(self, task_id: str) -> asyncio.Event:
        if task_id not in self._task_events:
            self._task_events[task_id] = asyncio.Event()
        return self._task_events[task_id]

    def has_active_workers(self, harness: str | None = None) -> bool:
        """Check if any active worker is connected supporting the specified harness."""
        if not harness:
            return bool(self._active_workers)
        norm = harness.lower().strip()
        return any(norm in [h.lower() for h in w.harnesses] for w in self._active_workers.values())

    async def submit_task(self, spec: TaskSpec) -> TaskRecord:
        """Persist a task spec and offer it to an eligible active worker."""
        task_id = spec.task_id or str(uuid.uuid4())
        session_id = spec.session_id or str(uuid.uuid4())
        spec.task_id = task_id
        spec.session_id = session_id

        task = TaskRecord(
            task_id=task_id,
            session_id=session_id,
            harness=spec.harness,
            prompt=spec.prompt,
            workspace_mode=spec.workspace_mode,
            repo_root=spec.repo_root,
            timeout_seconds=spec.timeout_seconds,
            detach=spec.detach,
            status="pending",
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.store.save_task(task)
        self._get_task_event(task_id)

        # Attempt immediate dispatch
        await self._dispatch_task_offer(task)
        return task

    async def _dispatch_task_offer(self, task: TaskRecord) -> bool:
        """Offer task to an eligible worker taking session affinity into account."""
        # 1. Check sticky session affinity
        affinity_worker_id = self.store.get_session_affinity(task.session_id)
        candidate_worker_id: str | None = None

        if affinity_worker_id and affinity_worker_id in self._worker_queues:
            # Affinity worker is currently connected and active
            candidate_worker_id = affinity_worker_id
        elif not affinity_worker_id:
            # First turn: find any active worker supporting target harness
            for w_id, w_info in self._active_workers.items():
                if task.harness in w_info.harnesses and w_id in self._worker_queues:
                    candidate_worker_id = w_id
                    break

        if candidate_worker_id and candidate_worker_id in self._worker_queues:
            payload = {
                "event": "task_offer",
                "task_id": task.task_id,
                "session_id": task.session_id,
                "harness": task.harness,
                "prompt": task.prompt,
                "workspace_mode": task.workspace_mode,
                "repo_root": task.repo_root,
                "timeout_seconds": task.timeout_seconds,
            }
            try:
                self._worker_queues[candidate_worker_id].put_nowait(payload)
                task.status = "offered"
                self.store.save_task(task)
                logger.info(
                    "Offered task '%s' (harness=%s, session=%s) to worker '%s'",
                    task.task_id,
                    task.harness,
                    task.session_id,
                    candidate_worker_id,
                )
                return True
            except asyncio.QueueFull:
                logger.warning("Worker queue full for '%s', task pending", candidate_worker_id)

        return False

    async def wait_for_task_completion(
        self, task_id: str, timeout: float | None = None
    ) -> TaskResult:
        """Wait for task completion event, polling with timeout protection."""
        event = self._get_task_event(task_id)
        effective_timeout = timeout if timeout is not None else 300.0

        try:
            await asyncio.wait_for(event.wait(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            self.store.clean_expired_leases(grace_period_seconds=0.0)
            task = self.store.get_task(task_id)
            if task and task.status == "completed" and task.result:
                return task.result
            raise WorkerTimeoutError(
                f"Task '{task_id}' timed out after {effective_timeout}s waiting for execution completion."
            )

        task = self.store.get_task(task_id)
        if not task:
            raise RuntimeError(f"Task '{task_id}' record disappeared from store")

        if task.status == "completed" and task.result:
            return task.result
        elif task.status == "cancelled":
            return TaskResult(
                session_id=task.session_id,
                harness=task.harness,
                status="cancelled",
                output="Task cancelled by user or orchestrator.",
                exit_code=130,
                task_id=task.task_id,
            )
        else:
            err_msg = task.error or f"Task execution failed with status: {task.status}"
            return TaskResult(
                session_id=task.session_id,
                harness=task.harness,
                status="failed",
                output=err_msg,
                exit_code=1,
                task_id=task.task_id,
            )

    async def subscribe_worker(
        self,
        worker_id: str,
        harnesses: list[str],
        device_name: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Worker SSE connection lifecycle. Yields task offers and keepalives."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._worker_queues[worker_id] = queue

        worker_info = WorkerInfo(
            worker_id=worker_id,
            harnesses=harnesses,
            connected_at=time.time(),
            last_seen_at=time.time(),
            is_active=True,
            device_name=device_name,
        )
        self._active_workers[worker_id] = worker_info
        self.store.register_worker(worker_info)
        logger.info(
            "Worker '%s' connected (harnesses=%s, device=%s)",
            worker_id,
            harnesses,
            device_name,
        )

        # Check for any pending tasks waiting for this worker's harnesses
        await self._drain_pending_tasks_for_worker(worker_id, harnesses)

        try:
            while self._running:
                try:
                    # Wait up to 15s for an event, then send keepalive ping comment
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield item
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "keepalive"}
                    self.store.heartbeat_worker(worker_id)
        finally:
            self._worker_queues.pop(worker_id, None)
            self._active_workers.pop(worker_id, None)
            self.store.deactivate_worker(worker_id)
            logger.info("Worker '%s' disconnected", worker_id)

    async def _drain_pending_tasks_for_worker(self, worker_id: str, harnesses: list[str]) -> None:
        """Scan SQLite store for pending/offered tasks that can be fulfilled by newly connected worker."""
        # Check all pending tasks
        with self.store._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status IN ('pending', 'offered') ORDER BY created_at ASC"
            ).fetchall()
            for r in rows:
                task = self.store._row_to_task(r)
                if task.harness in harnesses:
                    affinity = self.store.get_session_affinity(task.session_id)
                    if affinity is None or affinity == worker_id:
                        await self._dispatch_task_offer(task)

    def ack_task(self, task_id: str, worker_id: str, lease_seconds: float = 45.0) -> bool:
        """Acknowledge and claim a task lease."""
        success = self.store.claim_task(task_id, worker_id, lease_seconds=lease_seconds)
        if success:
            task = self.store.get_task(task_id)
            if task:
                # Bind session affinity so future turns stay on this worker
                self.store.set_session_affinity(task.session_id, worker_id)
            logger.info(
                "Task '%s' claimed by worker '%s' (lease: %ss)", task_id, worker_id, lease_seconds
            )
        return success

    def heartbeat_task(self, task_id: str, worker_id: str, lease_seconds: float = 45.0) -> bool:
        """Renew active sliding lease."""
        success = self.store.renew_lease(task_id, worker_id, lease_seconds=lease_seconds)
        self.store.heartbeat_worker(worker_id)
        return success

    def complete_task(self, task_id: str, worker_id: str, result: TaskResult) -> bool:
        """Complete task with final execution result."""
        result.task_id = task_id
        success = self.store.complete_task(task_id, worker_id, result)
        if success:
            logger.info("Task '%s' completed successfully by worker '%s'", task_id, worker_id)
            if task_id in self._task_events:
                self._task_events[task_id].set()
        return success

    def fail_task(self, task_id: str, worker_id: str, error: str) -> bool:
        """Record task failure."""
        success = self.store.fail_task(task_id, worker_id, error)
        if success:
            logger.warning("Task '%s' marked failed by worker '%s': %s", task_id, worker_id, error)
            if task_id in self._task_events:
                self._task_events[task_id].set()
        return success

    def cancel_task(self, task_id: str) -> bool:
        """Cancel task and notify listeners."""
        success = self.store.cancel_task(task_id)
        if success:
            logger.info("Task '%s' cancelled", task_id)
            if task_id in self._task_events:
                self._task_events[task_id].set()
        return success

    async def _lease_watchdog_loop(self) -> None:
        """Periodic background loop cleaning up abandoned tasks and expired leases."""
        while self._running:
            try:
                await asyncio.sleep(10.0)
                expired_task_ids = self.store.clean_expired_leases(grace_period_seconds=30.0)
                for t_id in expired_task_ids:
                    logger.warning(
                        "Task '%s' lease expired without worker renewal; marked timeout", t_id
                    )
                    if t_id in self._task_events:
                        self._task_events[t_id].set()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in lease watchdog loop: %s", exc)
