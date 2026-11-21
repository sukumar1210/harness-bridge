from __future__ import annotations

import asyncio
import logging
import os
import platform
from typing import Any

from harness_bridge.core.types import TaskSpec
from harness_bridge.drivers.registry import list_all_harness_info
from harness_bridge.relay.bus import RelayBus
from harness_bridge.session.manager import SessionManager

logger = logging.getLogger("harness-bridge.relay.embedded")


class EmbeddedWorker:
    """In-process worker thread/coroutine that auto-spawns inside `serve` for local harnesses."""

    def __init__(
        self,
        relay_bus: RelayBus,
        session_manager: SessionManager | None = None,
        worker_id: str | None = None,
        harnesses: list[str] | None = None,
    ) -> None:
        self.relay_bus = relay_bus
        self.session_manager = session_manager or SessionManager()
        host_name = platform.node() or "local"
        self.worker_id = worker_id or f"embedded-{host_name}-{os.getpid()}"

        if harnesses is not None:
            self.harnesses = harnesses
        else:
            # Auto-detect locally installed harnesses
            detected = [h.name for h in list_all_harness_info() if h.installed]
            self.harnesses = detected

        self._running = False
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start listening for tasks from the relay bus."""
        if not self.harnesses:
            logger.info("Embedded worker found no locally installed harnesses; staying idle.")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._run_loop())
        logger.info(
            "Embedded worker '%s' started with harnesses: %s",
            self.worker_id,
            self.harnesses,
        )

    async def stop(self) -> None:
        """Stop worker task."""
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Embedded worker '%s' stopped", self.worker_id)

    async def _run_loop(self) -> None:
        """Consume tasks from subscribe_worker generator."""
        while self._running:
            try:
                subscription = self.relay_bus.subscribe_worker(
                    worker_id=self.worker_id,
                    harnesses=self.harnesses,
                    device_name=platform.node(),
                )
                async for event in subscription:
                    if not self._running:
                        break
                    event_type = event.get("event")
                    if event_type == "task_offer":
                        asyncio.create_task(self._handle_task(event))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "Embedded worker encountered error in event stream: %s. Reconnecting...", exc
                )
                await asyncio.sleep(1.0)

    async def _handle_task(self, event: dict[str, Any]) -> None:
        """Acknowledge, execute, and return task results."""
        task_id = event["task_id"]
        session_id = event["session_id"]
        harness = event["harness"]

        # 1. Acknowledge task lease
        if not self.relay_bus.ack_task(task_id, self.worker_id, lease_seconds=45.0):
            logger.warning("Embedded worker failed to claim task '%s'", task_id)
            return

        spec = TaskSpec(
            harness=harness,
            prompt=event["prompt"],
            session_id=session_id,
            task_id=task_id,
            workspace_mode=event.get("workspace_mode", "inherit"),
            timeout_seconds=event.get("timeout_seconds", 300),
            repo_root=event.get("repo_root"),
        )

        # 2. Heartbeat task in background while executing
        heartbeat_active = True

        async def _heartbeat_loop() -> None:
            while heartbeat_active:
                await asyncio.sleep(15.0)
                if not heartbeat_active:
                    break
                self.relay_bus.heartbeat_task(task_id, self.worker_id, lease_seconds=45.0)

        hb_task = asyncio.create_task(_heartbeat_loop())

        try:
            result = await self.session_manager.execute_task(spec)
            result.task_id = task_id
            self.relay_bus.complete_task(task_id, self.worker_id, result)
        except Exception as exc:
            logger.error("Embedded worker failed executing task '%s': %s", task_id, exc)
            self.relay_bus.fail_task(task_id, self.worker_id, str(exc))
        finally:
            heartbeat_active = False
            hb_task.cancel()
            try:
                await hb_task
            except asyncio.CancelledError:
                pass
